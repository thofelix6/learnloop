"""Course registry: plan resolution, session directories, workbook write-back."""
from __future__ import annotations

from pathlib import Path

from . import config, db, pdfsplit, plan


def sessions_dir(slug: str) -> Path:
    d = config.SESSIONS_DIR if slug == 'build-llm' else config.SESSIONS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_default_course() -> int:
    cfg = config.load()
    return db.upsert_course(
        'build-llm',
        'Build Your Own LLM',
        '30 sessions · Parts I-IV · from an empty folder to a working GPT',
        kind='workbook', workbook=cfg.get('workbook', ''), guide=cfg.get('guide', ''),
        position=1)


def all_courses() -> list[dict]:
    return [dict(r) for r in db.list_courses()]


def get_plan(slug: str) -> dict:
    course = db.get_course(slug)
    if not course:
        raise KeyError(f'no course {slug!r}')

    if course['kind'] == 'workbook':
        data = plan.read_plan(course['workbook'])
    else:
        rows = db.course_sessions(int(course['id']))
        sessions = []
        for r in rows:
            rng = plan.parse_pages(r['pages'] or '')
            sessions.append({
                'n': r['n'], 'date': r['date'], 'weekday': r['weekday'] or '',
                'week': r['week'], 'block': r['block'] or '', 'what': r['what'] or '',
                'pages': r['pages'] or '', 'range': list(rng) if rng else [],
                'deliverable': r['deliverable'] or '', 'minutes': r['minutes'] or 0,
                'done_xlsx': False,
            })
        dates = [s['date'] for s in sessions if s['date']]
        data = {
            'start': dates[0] if dates else None,
            'end': dates[-1] if dates else None,
            'total_minutes': sum(s['minutes'] for s in sessions),
            'count': len(sessions),
            'today': sessions[0]['n'] if sessions else None,
            'sessions': sessions,
        }

    data['course'] = {'slug': course['slug'], 'title': course['title'],
                      'subtitle': course['subtitle'], 'kind': course['kind'],
                      'guide': course['guide']}
    # attach files and exercise counts
    directory = sessions_dir(slug)
    ex_by_chapter = {}
    for ex in db.list_exercises(int(course['id'])):
        ex_by_chapter.setdefault(ex['chapter'], []).append(ex['slug'])
    for s in data['sessions']:
        f = pdfsplit.file_for(n=s['n'], directory=directory)
        s['file'] = f.name if f else None
        s['has_file'] = bool(f)
        s['exercises'] = ex_by_chapter.get(_chapter_of(s.get('block', '')), [])
    return data


def _chapter_of(block: str) -> int:
    """Map a session block to the exercise chapter code.

    'Chapter 3 - Strings' -> 3
    'Part I - Ch 1'       -> 1
    'Lab 2 (2/3)'         -> 102   (labs live at 100 + n)
    """
    import re
    text = block or ''
    m = re.search(r'chapter\s*(\d+)', text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'\bch\s*(\d+)', text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'\blab\s*(\d+)', text, re.I)
    if m:
        return 100 + int(m.group(1))
    return 0


def set_done(slug: str, n: int, done: bool) -> tuple[bool, str]:
    course = db.get_course(slug)
    if not course:
        return False, 'unknown course'
    if course['kind'] == 'workbook':
        return plan.set_done_safe(n, done)
    return True, ''


def split_course(slug: str, force: bool = False) -> dict:
    course = db.get_course(slug)
    if not course:
        raise KeyError(slug)
    data = get_plan(slug)
    return pdfsplit.split_generic(
        guide=Path(course['guide']),
        sessions=data['sessions'],
        out_dir=sessions_dir(slug),
        force=force)
