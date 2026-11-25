"""LearnLoop - a multi-course study app with auto-graded exercises."""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, courses, db, grader, nas, notes, pdfsplit, plan, security, site

app = FastAPI(title='LearnLoop', docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=500)
site.install(app)

COOKIE = 'll_session'
TOKEN_DAYS = 30
_CSRF_HEADER = 'x-learnloop'
DEFAULT_COURSE = 'build-llm'
AUDIO_DIR = config.DATA / 'audio'
VIDEO_DIR = config.DATA / 'video'

# account fields are validated on the server too - the browser can be bypassed
USERNAME_RE = re.compile(r'^[A-Za-z0-9._-]{3,32}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s.]+\.[A-Za-z]{2,}$')

db.init()
courses.ensure_default_course()

app.mount('/static', StaticFiles(directory=str(config.STATIC)), name='static')


# --------------------------------------------------------------------- helpers
def _csrf_ok(request: Request) -> bool:
    return request.headers.get(_CSRF_HEADER) == '1'


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.lookup_token(security.token_fingerprint(token))
    if not row:
        return None
    try:
        if datetime.fromisoformat(row['expires_at']) < datetime.now(timezone.utc):
            db.drop_token(row['token_hash'])
            return None
    except Exception:
        return None
    if row['status'] != 'approved':
        return None
    return row


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail='not signed in')
    return user


def require_admin(request: Request):
    user = require_user(request)
    if user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='admin only')
    return user


def _user_json(row) -> dict:
    d = dict(row)
    return {'id': d.get('id') or d.get('user_id'), 'username': d.get('username'),
            'email': d.get('email') or '', 'role': d.get('role'), 'status': d.get('status'),
            'created_at': d.get('created_at'), 'last_login': d.get('last_login')}


def _json(body, status: int = 200, headers: dict | None = None):
    return JSONResponse(content=body, status_code=status, headers=headers or {})


def _course_or_404(slug: str):
    course = db.get_course(slug or DEFAULT_COURSE)
    if not course:
        raise HTTPException(404, f'no course {slug!r}')
    return course


# --------------------------------------------------------------- rate limiting
_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_ATTEMPTS = 8
_WINDOW = 600


def _client_ip(request: Request) -> str:
    for header in ('cf-connecting-ip', 'x-real-ip'):
        value = request.headers.get(header)
        if value:
            return value.strip()
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


def _too_many(ip: str) -> bool:
    now_ts = time.time()
    recent = [t for t in _ATTEMPTS[ip] if now_ts - t < _WINDOW]
    _ATTEMPTS[ip] = recent
    return len(recent) >= _MAX_ATTEMPTS


def _record_failure(ip: str) -> None:
    _ATTEMPTS[ip].append(time.time())


def _clear_failures(ip: str) -> None:
    _ATTEMPTS.pop(ip, None)


# ------------------------------------------------------- account validation
def _cookie_secure(request: Request) -> bool:
    """Only mark the session cookie Secure when the browser is really on HTTPS."""
    return site.is_https(request)


def _username_error(username: str) -> str | None:
    if not USERNAME_RE.match(username or ''):
        return 'username must be 3-32 characters: letters, digits, dot, dash or underscore'
    return None


def _password_error(password: str) -> str | None:
    if len(password) < 8:
        return 'password needs 8+ characters'
    if len(password) > 200:
        return 'password is too long'
    return None


def _email_error(email: str) -> str | None:
    if not email:
        return None
    if len(email) > 200 or not EMAIL_RE.match(email):
        return 'that email address does not look right'
    return None


# ------------------------------------------------------------------ anti-spam
# Signups are rare on a study app: a quiet hourly cap per address, a honeypot
# field and a minimum form dwell time stop scripted signups without a captcha.
_SIGNUPS: dict[str, list[float]] = defaultdict(list)
_MAX_SIGNUPS = 5
_SIGNUP_WINDOW = 3600
_MIN_FORM_MS = 1500


def _signup_allowed(ip: str) -> bool:
    now_ts = time.time()
    recent = [t for t in _SIGNUPS[ip] if now_ts - t < _SIGNUP_WINDOW]
    _SIGNUPS[ip] = recent
    return len(recent) < _MAX_SIGNUPS


def _record_signup(ip: str) -> None:
    _SIGNUPS[ip].append(time.time())


def _looks_automated(body: dict) -> bool:
    """True for a filled honeypot or a form submitted in less than a second."""
    if str(body.get('company') or body.get('website') or '').strip():
        return True
    try:
        started = int(body.get('t') or 0)
    except (TypeError, ValueError):
        started = 0
    if started:
        if started > 10 ** 12:                     # milliseconds
            elapsed_ms = time.time() * 1000 - started
        else:                                       # seconds
            elapsed_ms = (time.time() - started) * 1000
        if elapsed_ms < _MIN_FORM_MS:
            return True
    return False


# ----------------------------------------------------------------------- pages
@app.get('/')
def index(request: Request):
    return site.render_page('index.html', request)


@app.get('/manifest.webmanifest')
def manifest():
    return FileResponse(str(config.STATIC / 'manifest.webmanifest'),
                        media_type='application/manifest+json')


@app.get('/sw.js')
def service_worker():
    resp = FileResponse(str(config.STATIC / 'sw.js'), media_type='application/javascript')
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


# ------------------------------------------------------------------- auth api
@app.get('/api/state')
def api_state(request: Request):
    user = current_user(request)
    return _json({'setup_required': db.count_users() == 0,
                  'user': _user_json(user) if user else None, 'app': 'LearnLoop'})


@app.post('/api/setup')
async def api_setup(request: Request):
    if db.count_users() > 0:
        raise HTTPException(400, 'already set up')
    body = await request.json()
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''
    email = (body.get('email') or '').strip()
    for error in (_username_error(username), _password_error(password), _email_error(email)):
        if error:
            raise HTTPException(400, error)
    pw_hash, salt = security.hash_password(password)
    uid = db.create_user(username, pw_hash, salt, email,
                         role='admin', status='approved', approved_by='setup')
    config.update({'owner_username': username})
    db.log_event('setup', f'admin {username} created', uid)
    return _json({'ok': True, 'user_id': uid})


@app.post('/api/login')
async def api_login(request: Request):
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    ip = _client_ip(request)
    body = await request.json()
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''
    row = db.get_user(username)
    if not row or not security.verify_password(password, row['pw_hash'], row['pw_salt']):
        if _too_many(ip):
            db.log_event('login_throttled', ip)
            raise HTTPException(429, 'too many attempts - wait 10 minutes')
        _record_failure(ip)
        db.log_event('login_failed', f'{username} from {ip}')
        raise HTTPException(401, 'wrong username or password')
    if row['status'] != 'approved':
        _record_failure(ip)
        raise HTTPException(403, f"account is {row['status']} - an admin must approve it")
    _clear_failures(ip)
    token = security.new_token()
    expires = (datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)).isoformat(timespec='seconds')
    db.store_token(security.token_fingerprint(token), row['id'], expires,
                   request.headers.get('user-agent', ''), ip)
    db.touch_login(row['id'])
    db.log_event('login', username, row['id'])
    resp = _json({'ok': True, 'user': _user_json(row)})
    resp.set_cookie(COOKIE, token, max_age=TOKEN_DAYS * 86400, httponly=True,
                    samesite='lax', secure=_cookie_secure(request), path='/')
    return resp


@app.post('/api/signup')
async def api_signup(request: Request):
    """Request an account. Answers the same way when it looks automated."""
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    ip = _client_ip(request)
    body = await request.json()
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''
    email = (body.get('email') or '').strip()

    def _soft_ok():
        return _json({'ok': True, 'status': 'pending',
                      'message': 'Account created. An admin has to approve it before you can sign in.'})

    # silent rejections: honeypot, impossible speed, hourly cap
    if _looks_automated(body) or not _signup_allowed(ip):
        db.log_event('signup_blocked', f'{ip} (filtered)')
        return _soft_ok()

    for error in (_username_error(username), _password_error(password), _email_error(email)):
        if error:
            raise HTTPException(400, error)
    if db.get_user(username):
        raise HTTPException(409, 'that username is taken')
    _record_signup(ip)
    pw_hash, salt = security.hash_password(password)
    uid = db.create_user(username, pw_hash, salt, email,
                         role='user', status='pending')
    db.log_event('signup', f'{username} requested an account', uid)
    return _soft_ok()


@app.post('/api/logout')
def api_logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        db.drop_token(security.token_fingerprint(token))
    resp = _json({'ok': True})
    resp.delete_cookie(COOKIE, path='/', secure=_cookie_secure(request), httponly=True,
                       samesite='lax')
    return resp


@app.get('/api/me')
def api_me(request: Request):
    return _json({'user': _user_json(require_user(request))})


# ------------------------------------------------------------------ courses
@app.get('/api/courses')
def api_courses(request: Request):
    user = require_user(request)
    out = []
    for c in db.list_courses():
        cid = int(c['id'])
        try:
            data = courses.get_plan(c['slug'])
            total = data['count']
        except Exception:
            total = 0
        prog = db.get_progress(user['id'], cid)
        ex_prog = db.exercise_progress(user['id'], cid)
        total_ex = len(db.list_exercises(cid))
        out.append({
            'id': cid, 'slug': c['slug'], 'title': c['title'], 'subtitle': c['subtitle'],
            'kind': c['kind'], 'sessions': total,
            'done': sum(1 for v in prog.values() if v.get('done')),
            'exercises': total_ex,
            'exercises_passed': sum(1 for v in ex_prog.values() if v.get('passed')),
        })
    return _json({'courses': out})


@app.get('/api/plan')
def api_plan(request: Request):
    user = require_user(request)
    slug = request.query_params.get('course') or DEFAULT_COURSE
    course = _course_or_404(slug)
    cid = int(course['id'])
    try:
        data = courses.get_plan(slug)
    except Exception as exc:
        raise HTTPException(500, f'could not read the plan: {exc}')

    prog = db.get_progress(user['id'], cid)
    ex_prog = db.exercise_progress(user['id'], cid)
    note_counts: dict[int, int] = {}
    for n in db.list_notes(user['id'], None, cid):
        note_counts[n['session_no']] = note_counts.get(n['session_no'], 0) + 1

    for s in data['sessions']:
        p = prog.get(s['n'], {})
        s['done'] = bool(p.get('done'))
        s['done_at'] = p.get('done_at')
        s['minutes_spent'] = int(p.get('minutes') or 0)
        s['notes'] = note_counts.get(s['n'], 0)
        s['exercise_slugs'] = s.get('exercises', [])
        s['exercises_passed'] = sum(1 for sl in s['exercise_slugs']
                                    if ex_prog.get(sl, {}).get('passed'))

    done = sum(1 for s in data['sessions'] if s['done'])
    data['done_count'] = done
    data['percent'] = round(100 * done / data['count'], 1) if data['count'] else 0
    data['minutes_done'] = sum(s['minutes'] for s in data['sessions'] if s['done'])
    data['minutes_spent'] = sum(s['minutes_spent'] for s in data['sessions'])
    data['next_session'] = next((s['n'] for s in data['sessions'] if not s['done']), None)
    data['exercise_total'] = len(db.list_exercises(cid))
    data['exercise_passed'] = sum(1 for v in ex_prog.values() if v.get('passed'))
    data['slug'] = slug
    return _json(data)


@app.post('/api/progress')
async def api_progress(request: Request):
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    slug = body.get('course') or DEFAULT_COURSE
    course = _course_or_404(slug)
    cid = int(course['id'])
    n = int(body.get('session') or 0)
    done = bool(body.get('done'))

    data = courses.get_plan(slug)
    session = next((s for s in data['sessions'] if s['n'] == n), None)
    if not session:
        raise HTTPException(404, 'no such session')

    db.set_done(user['id'], n, done, cid)
    warning = ''
    wrote_xlsx = False
    ok, msg = courses.set_done(slug, n, done)
    wrote_xlsx = ok
    if not ok:
        warning = msg
    try:
        notes.append_done(course['title'], session, done)
    except Exception as exc:
        warning = (warning + ' ' if warning else '') + f'vault not updated: {exc}'

    db.log_event('progress', f"{slug} session {n} -> {'done' if done else 'open'}", user['id'])
    return _json({'ok': True, 'session': n, 'done': done, 'xlsx': wrote_xlsx, 'warning': warning})


@app.post('/api/timer')
async def api_timer(request: Request):
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    course = _course_or_404(body.get('course') or DEFAULT_COURSE)
    n = int(body.get('session') or 0)
    minutes = int(body.get('minutes') or 0)
    total = db.add_minutes(user['id'], n, minutes, int(course['id']))
    return _json({'ok': True, 'session': n, 'minutes_spent': total})


@app.post('/api/notes')
async def api_notes_post(request: Request):
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    slug = body.get('course') or DEFAULT_COURSE
    course = _course_or_404(slug)
    cid = int(course['id'])
    n = int(body.get('session') or 0)
    text = (body.get('body') or '').strip()
    if not text:
        raise HTTPException(400, 'note is empty')
    data = courses.get_plan(slug)
    session = next((s for s in data['sessions'] if s['n'] == n), None)
    if not session:
        raise HTTPException(404, 'no such session')
    vault_path, warning = '', ''
    try:
        vault_path = notes.append_note(course['title'], session, text,
                                       minutes_spent=body.get('minutes_spent'),
                                       deliverable_done=bool(body.get('deliverable_done')))
    except Exception as exc:
        warning = f'vault not updated: {exc}'
    db.add_note(user['id'], n, text, vault_path, cid)
    db.log_event('note', f'{slug} session {n}', user['id'])
    return _json({'ok': True, 'vault_path': vault_path, 'warning': warning})


@app.get('/api/notes')
def api_notes_get(request: Request, session: int | None = None, course: str | None = None):
    user = require_user(request)
    c = _course_or_404(course or DEFAULT_COURSE)
    rows = db.list_notes(user['id'], session, int(c['id']))
    return _json({'notes': [dict(r) for r in rows]})


@app.get('/api/search')
def api_search(request: Request, q: str = '', course: str | None = None):
    user = require_user(request)
    needle = (q or '').strip().lower()
    if len(needle) < 2:
        return _json({'query': q, 'results': []})
    slug = course or DEFAULT_COURSE
    c = _course_or_404(slug)
    data = courses.get_plan(slug)
    results = []
    for s in data['sessions']:
        hay = ' '.join([str(s['block']), str(s['what']), str(s['deliverable']), str(s['pages'])]).lower()
        if needle in hay:
            snippet = s['what']
            idx = snippet.lower().find(needle)
            if idx > 40:
                snippet = '...' + snippet[max(0, idx - 30):idx + 90]
            results.append({'kind': 'session', 'session': s['n'],
                            'title': f"S{s['n']:02d} · {s['block']}",
                            'snippet': snippet, 'pages': s['pages']})
    for row in db.all_notes(user['id'], int(c['id'])):
        if needle in (row['body'] or '').lower():
            body = row['body']
            idx = body.lower().find(needle)
            results.append({'kind': 'note', 'session': row['session_no'],
                            'title': f"note · session {row['session_no']}",
                            'snippet': body[max(0, idx - 40):idx + 120], 'when': row['created_at']})
    for ex in db.list_exercises(int(c['id'])):
        hay = f"{ex['title']} {ex['prompt']}".lower()
        if needle in hay:
            results.append({'kind': 'exercise', 'slug': ex['slug'],
                            'title': f"exercise · {ex['title']}",
                            'snippet': (ex['prompt'] or '')[:140], 'chapter': ex['chapter']})
    return _json({'query': q, 'count': len(results), 'results': results[:40]})


# -------------------------------------------------------------------- pdf api
@app.get('/api/pdf/{n}')
def api_pdf(n: int, course: str | None = None):
    c = _course_or_404(course or DEFAULT_COURSE)
    f = pdfsplit.file_for(n, courses.sessions_dir(c['slug']))
    if not f or not f.exists():
        raise HTTPException(404, 'not split yet')
    return FileResponse(str(f), media_type='application/pdf', filename=f.name,
                        headers={'Cache-Control': 'no-store'})


# ----------------------------------------------------------------- audio api
AUDIO_COURSES = {'python-core', 'python-applied', 'build-llm'}


@app.get('/api/lecture')
def api_lecture(request: Request, course: str | None = None, session: int | None = None):
    """Where the narration for this session lives, if it has any."""
    require_user(request)
    slug = course or DEFAULT_COURSE
    _course_or_404(slug)
    n = int(session or 0)
    try:
        data = courses.get_plan(slug)
    except Exception as exc:
        raise HTTPException(500, f'could not read the plan: {exc}')
    s = next((x for x in data['sessions'] if x['n'] == n), None)
    if not s:
        raise HTTPException(404, 'no such session')

    m = re.search(r'Chapter\s+(\d+)', s.get('block') or '', re.I)
    if not m:
        if slug == 'build-llm':
            f = AUDIO_DIR / 'build-llm' / f's{n:02d}.mp3'
            if not f.exists():
                return _json({'available': False, 'reason': 'audio for this session is still being generated'},
                             headers={'Cache-Control': 'private, max-age=60'})
            return _json({'available': True, 'url': f'/audio/build-llm/s{n:02d}.mp3',
                          'title': s['block'], 'chapter': None,
                          'minutes': round(f.stat().st_size / 6000 / 60, 1)},
                         headers={'Cache-Control': 'private, max-age=300'})
        return _json({'available': False, 'reason': 'this course has no narration yet'},
                     headers={'Cache-Control': 'private, max-age=3600'})
    ch = int(m.group(1))
    folder = 'python-core' if ch <= 9 else 'python-applied'
    f = AUDIO_DIR / folder / f'ch{ch:02d}.mp3'
    if not f.exists():
        return _json({'available': False, 'reason': 'audio for this chapter is still being generated'},
                     headers={'Cache-Control': 'private, max-age=60'})
    return _json({
        'available': True,
        'url': f'/audio/{folder}/ch{ch:02d}.mp3',
        'title': s['block'],
        'chapter': ch,
        'minutes': round(f.stat().st_size / 6000 / 60, 1),
    }, headers={'Cache-Control': 'private, max-age=300'})


@app.get('/api/next-exercise')
def api_next_exercise(request: Request, course: str | None = None, session: int | None = None):
    """The exercise to open right after a session is marked done."""
    user = require_user(request)
    slug = course or DEFAULT_COURSE
    _course_or_404(slug)
    n = int(session or 0)
    try:
        data = courses.get_plan(slug)
    except Exception as exc:
        raise HTTPException(500, f'could not read the plan: {exc}')
    s = next((x for x in data['sessions'] if x['n'] == n), None)
    if not s:
        raise HTTPException(404, 'no such session')
    block = s.get('block') or ''

    chapter = None
    m = re.search(r'Chapter\s+(\d+)', block, re.I) or re.search(r'\bCh\s+(\d+)', block, re.I)
    if m:
        chapter = int(m.group(1))
    lab = re.search(r'\bLab\s+(\d+)', block, re.I)
    if lab:
        chapter = 100 + int(lab.group(1))

    cid = int(_course_or_404(slug)['id'])
    prog = db.exercise_progress(user['id'], cid)
    exercises = [dict(e) for e in db.list_exercises(cid)]
    pool = [e for e in exercises if chapter is not None and e['chapter'] == chapter]
    pick = next((e for e in pool if not prog.get(e['slug'], {}).get('passed')),
                pool[0] if pool else None)
    if not pick:
        return _json({'slug': None})
    return _json({'slug': pick['slug'], 'title': pick['title'],
                  'chapter': pick['chapter'], 'kind': pick['kind']})


@app.get('/api/video')
def api_video(request: Request, course: str | None = None, session: int | None = None):
    """The narrated lesson video for a session, if one has been rendered."""
    require_user(request)
    slug = course or DEFAULT_COURSE
    _course_or_404(slug)
    n = int(session or 0)
    f = VIDEO_DIR / slug / f's{n:02d}.mp4'
    if not f.exists():
        return _json({'available': False, 'reason': 'no video for this session yet'})
    return _json({'available': True, 'url': f'/video/{slug}/s{n:02d}.mp4',
                  'size_mb': round(f.stat().st_size / 1048576, 1)})


@app.get('/video/{folder}/{name}')
def video_file(folder: str, name: str):
    if folder not in AUDIO_COURSES or not re.fullmatch(r's\d{2}\.mp4', name):
        raise HTTPException(404, 'not found')
    f = VIDEO_DIR / folder / name
    if not f.exists():
        raise HTTPException(404, 'not found')
    return FileResponse(str(f), media_type='video/mp4',
                        headers={'Cache-Control': 'public, max-age=86400'})


@app.get('/api/reader')
def api_reader(request: Request, course: str | None = None, session: int | None = None):
    """Styled text of a session (extracted from the guide PDF for build-llm)."""
    require_user(request)
    slug = course or DEFAULT_COURSE
    _course_or_404(slug)
    n = int(session or 0)
    f = config.DATA / 'reader' / f'{slug}.json'
    if not f.exists():
        raise HTTPException(404, 'no reader content for this course')
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except Exception as exc:
        raise HTTPException(500, f'could not read the text: {exc}')
    s = next((x for x in data.get('sessions', []) if int(x.get('n', 0)) == n), None)
    if not s:
        raise HTTPException(404, 'no such session')
    return _json(s, headers={'Cache-Control': 'private, max-age=3600'})


@app.get('/audio/{folder}/{name}')
def audio_file(folder: str, name: str):
    if folder not in AUDIO_COURSES or not re.fullmatch(r'(ch|s)\d{2}\.mp3', name):
        raise HTTPException(404, 'not found')
    f = AUDIO_DIR / folder / name
    if not f.exists():
        raise HTTPException(404, 'not found')
    return FileResponse(str(f), media_type='audio/mpeg',
                        headers={'Cache-Control': 'public, max-age=86400'})


@app.post('/api/split')
def api_split(request: Request, course: str | None = None, force: bool = False):
    require_admin(request)
    slug = course or DEFAULT_COURSE
    try:
        result = courses.split_course(slug, force=force)
    except Exception as exc:
        raise HTTPException(500, f'split failed: {exc}')
    db.log_event('split', f"{slug}: {len(result['written'])} written")
    return _json(result)


# --------------------------------------------------------------- exercises api
@app.get('/api/exercises')
def api_exercises(request: Request, course: str | None = None):
    user = require_user(request)
    c = _course_or_404(course or DEFAULT_COURSE)
    prog = db.exercise_progress(user['id'], int(c['id']))
    out = []
    for ex in db.list_exercises(int(c['id'])):
        d = dict(ex)
        d.pop('solution', None)
        d['tests'] = len(json.loads(d.pop('tests_json') or '[]'))
        d['hints'] = json.loads(d.pop('hints_json') or '[]')
        p = prog.get(ex['slug'], {})
        d['passed'] = bool(p.get('passed'))
        d['attempts'] = int(p.get('attempts') or 0)
        out.append(d)
    return _json({'course': c['slug'], 'exercises': out,
                  'passed': sum(1 for e in out if e['passed']), 'total': len(out)})


@app.get('/api/exercise/{slug}')
def api_exercise(slug: str, request: Request):
    ex = db.get_exercise_by_slug(slug)
    if not ex:
        raise HTTPException(404, 'no such exercise')
    d = dict(ex)
    d['kind'] = d.get('kind') or 'code'
    d['tests'] = json.loads(d.pop('tests_json') or '[]')
    d['hints'] = json.loads(d.pop('hints_json') or '[]')
    d['tests'] = [{'name': t.get('name', 'test')} for t in d['tests']]
    d.pop('solution', None)
    if d['kind'] == 'mcq':
        d['options'] = json.loads(d.pop('options') or '[]')
        d.pop('correct', None)          # graded on the server
        d.pop('explanation', None)      # only after a right answer
        d.pop('answer', None)
        d['answered'] = False
        d['choice'] = None
        user = current_user(request)
        if user:
            picked = db.passed_choice(int(user['id']), int(ex['id']))
            if picked is not None:
                d['answered'] = True     # already answered correctly: show it locked
                d['choice'] = picked
                d['explanation'] = ex['explanation'] or ''
    else:
        d.pop('options', None)
        d.pop('correct', None)
        d.pop('explanation', None)
        if d['kind'] != 'answer':
            d.pop('answer', None)      # never ship a model answer for graded code
    return _json(d)


@app.post('/api/exercise/{slug}/check')
async def api_exercise_check(slug: str, request: Request):
    """Answer a multiple-choice exercise; the right choice marks it done."""
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    try:
        choice = int(body.get('choice'))
    except Exception:
        raise HTTPException(400, 'choice must be an index')
    ex = db.get_exercise_by_slug(slug)
    if not ex:
        raise HTTPException(404, 'no such exercise')
    if (ex['kind'] or 'code') != 'mcq':
        raise HTTPException(400, 'not a multiple-choice exercise')
    options = json.loads(ex['options'] or '[]')
    if not (0 <= choice < len(options)):
        raise HTTPException(400, 'choice out of range')
    good = int(ex['correct']) == choice
    db.record_attempt(user['id'], int(ex['id']), f'choice:{choice}', good,
                      json.dumps({'correct': good, 'choice': choice}))
    db.log_event('exercise_check', f'{slug}: {"right" if good else "wrong"}', user['id'])
    if not good:
        return _json({'correct': False})
    return _json({'correct': True,
                  'explanation': ex['explanation'] or '',
                  'answer': ex['answer'] or ''})


@app.post('/api/exercise/{slug}/done')
async def api_exercise_done(slug: str, request: Request):
    """Self-mark a written exercise once you have compared your answer with the book's."""
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    ex = db.get_exercise_by_slug(slug)
    if not ex:
        raise HTTPException(404, 'no such exercise')
    if (ex['kind'] or 'code') != 'answer':
        raise HTTPException(400, 'only written exercises can be self-marked')
    db.record_attempt(user['id'], int(ex['id']), '', True, json.dumps({'self_marked': True}))
    db.log_event('exercise_done', slug, user['id'])
    return _json({'ok': True})


@app.post('/api/exercise/{slug}/run')
async def api_exercise_run(slug: str, request: Request):
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    ex = db.get_exercise_by_slug(slug)
    if not ex:
        raise HTTPException(404, 'no such exercise')
    if (ex['kind'] or 'code') != 'code':
        raise HTTPException(400, 'this is a written exercise - reveal the answer instead')
    body = await request.json()
    code = body.get('code') or ''
    if len(code) > 20000:
        raise HTTPException(400, 'code too long (20 KB limit)')
    tests = json.loads(ex['tests_json'] or '[]')
    result = grader.run(code, tests)
    db.record_attempt(user['id'], int(ex['id']), code,
                      bool(result.get('ok')), json.dumps(result)[:20000])
    db.log_event('exercise', f"{slug}: {'pass' if result.get('ok') else 'fail'}", user['id'])
    return _json(result)


# -------------------------------------------------------------------- nas api
@app.get('/api/nas/status')
def api_nas_status(request: Request, target: str = 'lan'):
    require_user(request)
    return _json(nas.status(target))


@app.post('/api/nas/upload')
async def api_nas_upload(request: Request):
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    target = body.get('target') or 'lan'
    slug = body.get('course') or DEFAULT_COURSE
    course = _course_or_404(slug)
    cid = int(course['id'])
    directory = courses.sessions_dir(slug)
    n = body.get('session')

    # Uploading into the shared course folder is maintenance, not studying: the PDFs
    # already live on the NAS, so only the admin may push them.
    if user['role'] != 'admin':
        raise HTTPException(403, 'uploading to the NAS folder is admin only')
    uploaded, failed, queued = [], [], []

    if n:
        try:
            result = nas.upload_session_file(int(n), target, directory=directory, slug=slug)
            uploaded.append(result['file'])
            db.clear_pending(int(n), cid)
        except Exception as exc:
            db.add_pending(int(n), target, str(exc), cid)
            failed.append({'session': int(n), 'error': str(exc)})
            queued.append(int(n))
    else:
        data = courses.get_plan(slug)
        todo = data['sessions']
        for i, s in enumerate(todo):
            try:
                result = nas.upload_session_file(s['n'], target, directory=directory, slug=slug)
                uploaded.append(result['file'])
                db.clear_pending(s['n'], cid)
            except Exception as exc:
                db.add_pending(s['n'], target, str(exc), cid)
                failed.append({'session': s['n'], 'error': str(exc)})
                queued.append(s['n'])
                if not uploaded:
                    for rest in todo[i + 1:]:
                        db.add_pending(rest['n'], target, 'queued after first failure', cid)
                        queued.append(rest['n'])
                    break

    db.log_event('nas_upload', f'{slug}: {len(uploaded)} ok, {len(queued)} queued', user['id'])
    return _json({'uploaded': uploaded, 'failed': failed, 'queued': queued,
                  'message': (f'{len(uploaded)} uploaded' if uploaded else 'NAS unreachable')
                             + (f', {len(queued)} queued for retry' if queued else '')})


@app.get('/api/nas/pending')
def api_nas_pending(request: Request):
    require_user(request)
    rows = db.list_pending()
    return _json({'count': len(rows), 'pending': [dict(r) for r in rows]})


@app.post('/api/nas/flush')
async def api_nas_flush(request: Request):
    user = require_user(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    target = body.get('target') or 'lan'
    rows = db.list_pending()
    ok = []
    for row in rows:
        n = int(row['session_no'])
        cid = int(row['course_id'])
        c = db.get_course_by_id(cid)
        try:
            res = nas.upload_session_file(n, target, directory=courses.sessions_dir(c['slug']), slug=c['slug'])
            db.clear_pending(n, cid)
            ok.append(res['file'])
        except Exception as exc:
            db.add_pending(n, target, str(exc), cid)
            if not ok:
                break
    db.log_event('nas_flush', f'{len(ok)} uploaded', user['id'])
    return _json({'uploaded': ok, 'remaining': db.count_pending(),
                  'message': f'{len(ok)} uploaded, {db.count_pending()} still queued'})


# ------------------------------------------------------------------- admin api
@app.get('/api/admin/users')
def api_admin_users(request: Request):
    require_admin(request)
    return _json({'users': [_user_json(r) for r in db.list_users()]})


@app.post('/api/admin/users/{uid}/status')
async def api_admin_status(uid: int, request: Request):
    admin = require_admin(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    status = body.get('status')
    if status not in ('approved', 'pending', 'rejected'):
        raise HTTPException(400, 'bad status')
    target = db.get_user_by_id(uid)
    if not target:
        raise HTTPException(404, 'no such user')
    if uid == admin['id'] and status != 'approved':
        raise HTTPException(400, 'you cannot lock yourself out')
    db.set_status(uid, status, admin['username'])
    db.log_event('user_status', f"{target['username']} -> {status}", admin['id'])
    return _json({'ok': True})


@app.post('/api/admin/users/{uid}/role')
async def api_admin_role(uid: int, request: Request):
    admin = require_admin(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    role = body.get('role')
    if role not in ('admin', 'user'):
        raise HTTPException(400, 'bad role')
    if uid == admin['id']:
        raise HTTPException(400, 'cannot change your own role')
    db.set_role(uid, role)
    return _json({'ok': True})


@app.delete('/api/admin/users/{uid}')
def api_admin_delete(uid: int, request: Request):
    admin = require_admin(request)
    if uid == admin['id']:
        raise HTTPException(400, 'cannot delete yourself')
    db.delete_user(uid)
    db.log_event('user_delete', f'user {uid}', admin['id'])
    return _json({'ok': True})


@app.get('/api/config')
def api_config_get(request: Request):
    require_admin(request)
    return _json(config.public_view(config.load()))


@app.post('/api/config')
async def api_config_post(request: Request):
    admin = require_admin(request)
    if not _csrf_ok(request):
        raise HTTPException(400, 'missing header')
    body = await request.json()
    patch = {k: body[k] for k in ('workbook', 'guide', 'vault', 'owner_username') if k in body}
    site_patch = {}
    incoming_site = body.get('site') or {}
    for key in ('name', 'tagline', 'public_url', 'contact_email', 'effective_date',
                'operator', 'jurisdiction'):
        if key in incoming_site:
            site_patch[key] = str(incoming_site[key] or '').strip()
    if site_patch:
        patch['site'] = site_patch
    nas_patch = {}
    incoming = body.get('nas') or {}
    for key in ('lan_url', 'public_url', 'user', 'remote_dir', 'active'):
        if key in incoming:
            nas_patch[key] = incoming[key]
    if incoming.get('password'):
        nas_patch['password_enc'] = security.dpapi_encrypt(incoming['password'])
    if nas_patch:
        patch['nas'] = nas_patch
    cfg = config.update(patch)
    db.log_event('config', 'settings updated', admin['id'])
    return _json({'ok': True, 'config': config.public_view(cfg)})


@app.get('/api/events')
def api_events(request: Request):
    require_admin(request)
    return _json({'events': [dict(r) for r in db.recent_events(60)]})


# ---------------------------------------------------------------- analytics
@app.post('/api/hit')
async def api_hit(request: Request):
    """Count one page view. Cookieless and aggregate: no IP, no user agent, no id."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = str(body.get('path') or '')
    path = raw.split('?')[0].split('#')[0][:120]
    if not path.startswith('/'):
        path = '/'
    path = re.sub(r'/\d+', '/:n', path)               # session ids are not interesting
    ref = str(body.get('ref') or '')
    ref_host = ''
    if ref:
        try:
            from urllib.parse import urlsplit
            ref_host = urlsplit(ref).hostname or ''
        except Exception:
            ref_host = ''
    if ref_host and ref_host.lower() == (request.headers.get('host') or '').split(':')[0].lower():
        ref_host = ''                                  # internal navigation is not a referral
    db.add_pageview(path, datetime.now().date().isoformat(), ref_host)
    return _json({'ok': True})       # tiny body: sent with sendBeacon


@app.get('/api/analytics')
def api_analytics(request: Request, days: int = 14):
    require_admin(request)
    days = max(7, min(90, int(days or 14)))
    return _json(db.pageview_stats(days))


@app.get('/api/health')
def api_health():
    return _json({'ok': True, 'time': datetime.now().isoformat(timespec='seconds'),
                  'code_execution': grader.enabled()})
