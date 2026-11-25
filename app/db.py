"""SQLite storage: users, auth sessions, courses, per-course progress, notes, exercises."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    email        TEXT,
    pw_hash      TEXT NOT NULL,
    pw_salt      TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'user',
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    approved_at  TEXT,
    approved_by  TEXT,
    last_login   TEXT
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    user_agent   TEXT,
    ip           TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS courses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    subtitle     TEXT,
    kind         TEXT NOT NULL DEFAULT 'json',      -- 'workbook' | 'json'
    workbook     TEXT,
    guide        TEXT,
    plan_json    TEXT,
    position     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS course_sessions (
    course_id    INTEGER NOT NULL,
    n            INTEGER NOT NULL,
    date         TEXT,
    weekday      TEXT,
    week         INTEGER,
    block        TEXT,
    what         TEXT,
    pages        TEXT,
    deliverable  TEXT,
    minutes      INTEGER DEFAULT 0,
    PRIMARY KEY (course_id, n),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS progress (
    user_id      INTEGER NOT NULL,
    course_id    INTEGER NOT NULL DEFAULT 1,
    session_no   INTEGER NOT NULL,
    done         INTEGER NOT NULL DEFAULT 0,
    done_at      TEXT,
    minutes_spent INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, course_id, session_no),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    course_id    INTEGER NOT NULL DEFAULT 1,
    session_no   INTEGER NOT NULL,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    vault_path   TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exercises (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id    INTEGER NOT NULL,
    chapter      INTEGER NOT NULL,
    slug         TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    starter      TEXT,
    tests_json   TEXT NOT NULL,
    solution     TEXT,
    hints_json   TEXT,
    difficulty   TEXT DEFAULT 'medium',
    kind         TEXT NOT NULL DEFAULT 'code',   -- 'code' (graded) | 'answer' (show the answer) | 'mcq'
    answer       TEXT DEFAULT '',
    options      TEXT DEFAULT '',                 -- JSON array of choices, for mcq
    correct      INTEGER DEFAULT -1,              -- index of the right choice
    explanation  TEXT DEFAULT '',                 -- shown after a correct choice
    position     INTEGER DEFAULT 0,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exercise_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    exercise_id  INTEGER NOT NULL,
    code         TEXT NOT NULL,
    passed       INTEGER NOT NULL DEFAULT 0,
    results_json TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pending_uploads (
    session_no   INTEGER NOT NULL,
    course_id    INTEGER NOT NULL DEFAULT 1,
    target       TEXT NOT NULL DEFAULT 'lan',
    created_at   TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    last_try     TEXT,
    PRIMARY KEY (course_id, session_no)
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,
    kind         TEXT NOT NULL,
    detail       TEXT,
    created_at   TEXT NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    con = getattr(_local, 'con', None)
    if con is None:
        con = sqlite3.connect(config.DB_PATH, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys = ON')
        con.execute('PRAGMA journal_mode = WAL')
        _local.con = con
    return con


@contextmanager
def cursor():
    con = _conn()
    cur = con.cursor()
    try:
        yield cur
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _columns(cur, table: str) -> list[str]:
    cur.execute(f'PRAGMA table_info({table})')
    return [r['name'] for r in cur.fetchall()]


def _table_exists(cur, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def init() -> None:
    """Create the schema, then upgrade a legacy single-course database in place."""
    with cursor() as cur:
        cur.executescript(SCHEMA)
        _migrate_legacy(cur)


def _migrate_legacy(cur) -> None:
    """Older installs had no course_id. Rebuild those tables, keeping the data."""
    if 'course_id' not in _columns(cur, 'progress'):
        cur.execute('ALTER TABLE progress RENAME TO progress_old')
        cur.execute("""CREATE TABLE progress (
            user_id INTEGER NOT NULL, course_id INTEGER NOT NULL DEFAULT 1,
            session_no INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
            done_at TEXT, minutes_spent INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, course_id, session_no))""")
        cur.execute("""INSERT INTO progress (user_id, course_id, session_no, done, done_at, minutes_spent)
                       SELECT user_id, 1, session_no, done, done_at, minutes_spent FROM progress_old""")
        cur.execute('DROP TABLE progress_old')

    if 'course_id' not in _columns(cur, 'notes'):
        cur.execute('ALTER TABLE notes ADD COLUMN course_id INTEGER NOT NULL DEFAULT 1')

    if 'course_id' not in _columns(cur, 'pending_uploads'):
        cur.execute('ALTER TABLE pending_uploads RENAME TO pending_old')
        cur.execute("""CREATE TABLE pending_uploads (
            session_no INTEGER NOT NULL, course_id INTEGER NOT NULL DEFAULT 1,
            target TEXT NOT NULL DEFAULT 'lan', created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, last_try TEXT,
            PRIMARY KEY (course_id, session_no))""")
        cur.execute("""INSERT INTO pending_uploads (session_no, course_id, target, created_at, attempts, last_error, last_try)
                       SELECT session_no, 1, target, created_at, attempts, last_error, last_try FROM pending_old""")
        cur.execute('DROP TABLE pending_old')

    # exercises gained kind/answer when the written questions were added
    cols = _columns(cur, 'exercises')
    if 'kind' not in cols:
        cur.execute("ALTER TABLE exercises ADD COLUMN kind TEXT NOT NULL DEFAULT 'code'")
    if 'answer' not in cols:
        cur.execute("ALTER TABLE exercises ADD COLUMN answer TEXT DEFAULT ''")

    # multiple-choice versions of the written questions
    cols = _columns(cur, 'exercises')
    if 'options' not in cols:
        cur.execute("ALTER TABLE exercises ADD COLUMN options TEXT DEFAULT ''")
    if 'correct' not in cols:
        cur.execute('ALTER TABLE exercises ADD COLUMN correct INTEGER DEFAULT -1')
    if 'explanation' not in cols:
        cur.execute("ALTER TABLE exercises ADD COLUMN explanation TEXT DEFAULT ''")


# ------------------------------------------------------------------- courses
def upsert_course(slug: str, title: str, subtitle: str = '', kind: str = 'json',
                  workbook: str = '', guide: str = '', plan_json: str = '',
                  position: int = 0) -> int:
    with cursor() as cur:
        cur.execute('SELECT id FROM courses WHERE slug=?', (slug,))
        row = cur.fetchone()
        if row:
            cur.execute("""UPDATE courses SET title=?, subtitle=?, kind=?, workbook=?, guide=?,
                           plan_json=?, position=? WHERE id=?""",
                        (title, subtitle, kind, workbook, guide, plan_json, position, row['id']))
            return int(row['id'])
        cur.execute("""INSERT INTO courses (slug, title, subtitle, kind, workbook, guide, plan_json, position, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (slug, title, subtitle, kind, workbook, guide, plan_json, position, now()))
        return int(cur.lastrowid)


def list_courses():
    with cursor() as cur:
        cur.execute('SELECT * FROM courses ORDER BY position, id')
        return cur.fetchall()


def get_course(slug: str):
    with cursor() as cur:
        cur.execute('SELECT * FROM courses WHERE slug=?', (slug,))
        return cur.fetchone()


def get_course_by_id(cid: int):
    with cursor() as cur:
        cur.execute('SELECT * FROM courses WHERE id=?', (cid,))
        return cur.fetchone()


def set_course_sessions(course_id: int, sessions: list[dict]) -> int:
    with cursor() as cur:
        cur.execute('DELETE FROM course_sessions WHERE course_id=?', (course_id,))
        for s in sessions:
            cur.execute("""INSERT INTO course_sessions
                (course_id, n, date, weekday, week, block, what, pages, deliverable, minutes)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (course_id, s['n'], s.get('date'), s.get('weekday'), s.get('week'),
                         s.get('block'), s.get('what'), s.get('pages'), s.get('deliverable'),
                         int(s.get('minutes') or 0)))
        return len(sessions)


def course_sessions(course_id: int) -> list[dict]:
    with cursor() as cur:
        cur.execute('SELECT * FROM course_sessions WHERE course_id=? ORDER BY n', (course_id,))
        return [dict(r) for r in cur.fetchall()]


# --------------------------------------------------------------------- users
def count_users() -> int:
    with cursor() as cur:
        cur.execute('SELECT COUNT(*) AS c FROM users')
        return int(cur.fetchone()['c'])


def create_user(username: str, pw_hash: str, pw_salt: str, email: str = '',
                role: str = 'user', status: str = 'pending', approved_by: str = '') -> int:
    with cursor() as cur:
        cur.execute(
            'INSERT INTO users (username, email, pw_hash, pw_salt, role, status, created_at, approved_at, approved_by)'
            ' VALUES (?,?,?,?,?,?,?,?,?)',
            (username, email, pw_hash, pw_salt, role, status, now(),
             now() if status == 'approved' else None, approved_by or None))
        return int(cur.lastrowid)


def get_user(username: str):
    with cursor() as cur:
        cur.execute('SELECT * FROM users WHERE lower(username)=lower(?)', (username,))
        return cur.fetchone()


def get_user_by_id(uid: int):
    with cursor() as cur:
        cur.execute('SELECT * FROM users WHERE id=?', (uid,))
        return cur.fetchone()


def list_users():
    with cursor() as cur:
        cur.execute('SELECT * FROM users ORDER BY status DESC, created_at DESC')
        return cur.fetchall()


def set_status(uid: int, status: str, by: str = '') -> None:
    with cursor() as cur:
        cur.execute('UPDATE users SET status=?, approved_at=?, approved_by=? WHERE id=?',
                    (status, now() if status == 'approved' else None, by or None, uid))


def set_role(uid: int, role: str) -> None:
    with cursor() as cur:
        cur.execute('UPDATE users SET role=? WHERE id=?', (role, uid))


def delete_user(uid: int) -> None:
    with cursor() as cur:
        cur.execute('DELETE FROM users WHERE id=?', (uid,))


def touch_login(uid: int) -> None:
    with cursor() as cur:
        cur.execute('UPDATE users SET last_login=? WHERE id=?', (now(), uid))


# ------------------------------------------------------------ auth tokens
def store_token(token_hash: str, uid: int, expires: str, ua: str = '', ip: str = '') -> None:
    with cursor() as cur:
        cur.execute('INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at, user_agent, ip)'
                    ' VALUES (?,?,?,?,?,?)', (token_hash, uid, now(), expires, ua[:300], ip))


def lookup_token(token_hash: str):
    with cursor() as cur:
        cur.execute(
            'SELECT s.*, u.id AS id, u.username, u.email, u.role, u.status, u.created_at AS created_at,'
            ' u.last_login AS last_login FROM auth_sessions s'
            ' JOIN users u ON u.id = s.user_id WHERE s.token_hash=?', (token_hash,))
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        data['id'] = data.get('id') or data.get('user_id')
        data['user_id'] = data.get('user_id') or data['id']
        return data


def drop_token(token_hash: str) -> None:
    with cursor() as cur:
        cur.execute('DELETE FROM auth_sessions WHERE token_hash=?', (token_hash,))


def purge_expired() -> None:
    with cursor() as cur:
        cur.execute('DELETE FROM auth_sessions WHERE expires_at < ?', (now(),))


# -------------------------------------------------------------- progress
def get_progress(uid: int, course_id: int = 1) -> dict:
    with cursor() as cur:
        cur.execute('SELECT session_no, done, done_at, minutes_spent FROM progress'
                    ' WHERE user_id=? AND course_id=?', (uid, course_id))
        return {int(r['session_no']): dict(done=bool(r['done']), done_at=r['done_at'],
                                           minutes=int(r['minutes_spent'] or 0))
                for r in cur.fetchall()}


def set_done(uid: int, session_no: int, done: bool, course_id: int = 1) -> None:
    with cursor() as cur:
        cur.execute(
            'INSERT INTO progress (user_id, course_id, session_no, done, done_at) VALUES (?,?,?,?,?)'
            ' ON CONFLICT(user_id, course_id, session_no) DO UPDATE SET done=excluded.done, done_at=excluded.done_at',
            (uid, course_id, session_no, 1 if done else 0, now() if done else None))


def add_minutes(uid: int, session_no: int, minutes: int, course_id: int = 1) -> int:
    with cursor() as cur:
        cur.execute(
            'INSERT INTO progress (user_id, course_id, session_no, done, minutes_spent) VALUES (?,?,?,0,?)'
            ' ON CONFLICT(user_id, course_id, session_no) DO UPDATE SET minutes_spent = minutes_spent + excluded.minutes_spent',
            (uid, course_id, session_no, max(0, min(600, int(minutes)))))
        cur.execute('SELECT minutes_spent FROM progress WHERE user_id=? AND course_id=? AND session_no=?',
                    (uid, course_id, session_no))
        return int(cur.fetchone()['minutes_spent'] or 0)


# ----------------------------------------------------------------- notes
def add_note(uid: int, session_no: int, body: str, vault_path: str = '', course_id: int = 1) -> int:
    with cursor() as cur:
        cur.execute('INSERT INTO notes (user_id, course_id, session_no, body, created_at, vault_path)'
                    ' VALUES (?,?,?,?,?,?)', (uid, course_id, session_no, body, now(), vault_path))
        return int(cur.lastrowid)


def list_notes(uid: int, session_no: int | None = None, course_id: int = 1):
    with cursor() as cur:
        if session_no is None:
            cur.execute('SELECT * FROM notes WHERE user_id=? AND course_id=? ORDER BY created_at DESC LIMIT 200',
                        (uid, course_id))
        else:
            cur.execute('SELECT * FROM notes WHERE user_id=? AND course_id=? AND session_no=? ORDER BY created_at DESC',
                        (uid, course_id, session_no))
        return cur.fetchall()


def all_notes(uid: int, course_id: int | None = None):
    with cursor() as cur:
        if course_id is None:
            cur.execute('SELECT * FROM notes WHERE user_id=? ORDER BY created_at DESC', (uid,))
        else:
            cur.execute('SELECT * FROM notes WHERE user_id=? AND course_id=? ORDER BY created_at DESC',
                        (uid, course_id))
        return cur.fetchall()


# -------------------------------------------------------------- exercises
def upsert_exercise(course_id: int, chapter: int, slug: str, title: str, prompt: str,
                    starter: str, tests_json: str, solution: str, hints_json: str,
                    difficulty: str = 'medium', position: int = 0,
                    kind: str = 'code', answer: str = '') -> int:
    with cursor() as cur:
        cur.execute('SELECT id FROM exercises WHERE slug=?', (slug,))
        row = cur.fetchone()
        if row:
            cur.execute("""UPDATE exercises SET course_id=?, chapter=?, title=?, prompt=?, starter=?,
                           tests_json=?, solution=?, hints_json=?, difficulty=?, position=?,
                           kind=?, answer=? WHERE id=?""",
                        (course_id, chapter, title, prompt, starter, tests_json, solution,
                         hints_json, difficulty, position, kind, answer, row['id']))
            return int(row['id'])
        cur.execute("""INSERT INTO exercises (course_id, chapter, slug, title, prompt, starter,
                       tests_json, solution, hints_json, difficulty, position, kind, answer)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (course_id, chapter, slug, title, prompt, starter, tests_json, solution,
                     hints_json, difficulty, position, kind, answer))
        return int(cur.lastrowid)


def list_exercises(course_id: int):
    with cursor() as cur:
        cur.execute('SELECT * FROM exercises WHERE course_id=? ORDER BY chapter, position, id', (course_id,))
        return cur.fetchall()


def get_exercise(exercise_id: int):
    with cursor() as cur:
        cur.execute('SELECT * FROM exercises WHERE id=?', (exercise_id,))
        return cur.fetchone()


def get_exercise_by_slug(slug: str):
    with cursor() as cur:
        cur.execute('SELECT * FROM exercises WHERE slug=?', (slug,))
        return cur.fetchone()


def record_attempt(uid: int, exercise_id: int, code: str, passed: bool, results_json: str) -> int:
    with cursor() as cur:
        cur.execute("""INSERT INTO exercise_attempts (user_id, exercise_id, code, passed, results_json, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (uid, exercise_id, code, 1 if passed else 0, results_json, now()))
        return int(cur.lastrowid)


def passed_choice(uid: int, exercise_id: int) -> int | None:
    """The option a user picked when they last answered this MCQ correctly."""
    with cursor() as cur:
        row = cur.execute(
            "SELECT code FROM exercise_attempts WHERE user_id=? AND exercise_id=? "
            "AND passed=1 AND code LIKE 'choice:%' ORDER BY id DESC LIMIT 1",
            (uid, exercise_id)).fetchone()
    if not row:
        return None
    try:
        return int(row['code'].split(':', 1)[1])
    except (ValueError, IndexError):
        return None


def exercise_progress(uid: int, course_id: int) -> dict:
    """slug -> {passed: bool, attempts: int, last_at: str}"""
    with cursor() as cur:
        cur.execute("""SELECT e.slug, MAX(a.passed) AS passed, COUNT(a.id) AS attempts, MAX(a.created_at) AS last_at
                       FROM exercise_attempts a JOIN exercises e ON e.id = a.exercise_id
                       WHERE a.user_id=? AND e.course_id=? GROUP BY e.slug""", (uid, course_id))
        return {r['slug']: {'passed': bool(r['passed']), 'attempts': int(r['attempts']),
                            'last_at': r['last_at']} for r in cur.fetchall()}


# ---------------------------------------------------------- pending uploads
def add_pending(session_no: int, target: str, error: str, course_id: int = 1) -> None:
    with cursor() as cur:
        cur.execute(
            'INSERT INTO pending_uploads (session_no, course_id, target, created_at, attempts, last_error, last_try)'
            ' VALUES (?,?,?,?,1,?,?)'
            ' ON CONFLICT(course_id, session_no) DO UPDATE SET attempts = attempts + 1,'
            ' last_error = excluded.last_error, last_try = excluded.last_try',
            (session_no, course_id, target, now(), error[:400], now()))


def list_pending():
    with cursor() as cur:
        cur.execute('SELECT * FROM pending_uploads ORDER BY created_at')
        return cur.fetchall()


def clear_pending(session_no: int, course_id: int = 1) -> None:
    with cursor() as cur:
        cur.execute('DELETE FROM pending_uploads WHERE course_id=? AND session_no=?', (course_id, session_no))


def count_pending() -> int:
    with cursor() as cur:
        cur.execute('SELECT COUNT(*) AS c FROM pending_uploads')
        return int(cur.fetchone()['c'])


# ---------------------------------------------------------------- events
def log_event(kind: str, detail: str = '', uid: int | None = None) -> None:
    with cursor() as cur:
        cur.execute('INSERT INTO events (user_id, kind, detail, created_at) VALUES (?,?,?,?)',
                    (uid, kind, detail, now()))


def recent_events(limit: int = 50):
    with cursor() as cur:
        cur.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))
        return cur.fetchall()
