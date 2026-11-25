"""Append study notes into the Obsidian vault, one log per course."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import config

HEADER = """---
title: {title}
tags:
  - study
  - seeker
type: log
created: {date}
---

# {title}

Notes and deliverables captured in **LearnLoop**. The plan itself lives in [[{plan}]].

"""


def vault_dir() -> Path:
    cfg = config.load()
    return Path(cfg.get('vault') or '')


def log_name(course_title: str) -> str:
    return f'{course_title} Log.md'


def log_path(course_title: str) -> Path:
    return vault_dir() / log_name(course_title)


def _ensure(course_title: str) -> Path:
    vd = vault_dir()
    if not vd.exists():
        raise FileNotFoundError(f'vault not found: {vd}')
    path = log_path(course_title)
    if not path.exists():
        path.write_text(HEADER.format(title=f'{course_title} Log',
                                      date=datetime.now().strftime('%Y-%m-%d'),
                                      plan=course_title), encoding='utf-8')
    return path


def append_note(course_title: str, session: dict, body: str,
                minutes_spent: int | None = None, deliverable_done: bool = False) -> str:
    path = _ensure(course_title)
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"## Session {session['n']} - {session.get('block', '')}", '',
             f"`{stamp}` · {session.get('date', '')} · {session.get('pages', '')}"
             f" · planned {session.get('minutes', 0)} min"]
    if minutes_spent is not None:
        lines.append(f"· tracked **{minutes_spent} min**")
    if deliverable_done:
        lines += ['', f"**Deliverable done:** {session.get('deliverable', '')}"]
    lines += ['', body.strip() or '_(no text)_', '']
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return str(path)


def append_done(course_title: str, session: dict, done: bool) -> str:
    path = _ensure(course_title)
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    line = (f"- {'[x]' if done else '[ ]'} Session {session['n']} "
            f"({session.get('date', '')}) - {session.get('block', '')}  `{stamp}`\n")
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(line)
    return str(path)
