"""Read the study plan from the workbook and write the Done column back."""
from __future__ import annotations

import shutil
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import openpyxl

from . import config

_YES = ('yes', 'y', 'true', '1', 'x')


def _as_date(value, fallback: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + __import__('datetime').timedelta(days=float(value))).date()
        except Exception:
            return fallback
    return fallback


def parse_pages(text: str) -> tuple[int, int] | None:
    """'8-10' -> (8, 10);  '47' -> (47, 47)."""
    if not text:
        return None
    t = str(text).strip().replace('\u2013', '-').replace('p', '').replace('P', '')
    if '-' in t:
        a, _, b = t.partition('-')
        try:
            lo, hi = int(a.strip()), int(b.strip())
        except ValueError:
            return None
    else:
        try:
            lo = hi = int(t.strip())
        except ValueError:
            return None
    if lo <= 0 or hi < lo:
        return None
    return lo, hi


def read_plan(path: str | Path | None = None) -> dict:
    cfg = config.load()
    path = Path(path or cfg['workbook'])
    if not path.exists():
        raise FileNotFoundError(f'workbook not found: {path}')

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['Schedule'] if 'Schedule' in wb.sheetnames else wb.worksheets[0]
    start = _as_date(ws['B2'].value, date(2026, 11, 23))

    sessions = []
    for r in range(6, 36):
        n = ws.cell(r, 1).value
        if n is None:
            continue
        n = int(n)
        d = _as_date(ws.cell(r, 2).value,
                     start + __import__('datetime').timedelta(days=7 * ((n - 1) // 5) + ((n - 1) % 5)))
        pages = str(ws.cell(r, 7).value or '').strip()
        sessions.append({
            'n': n,
            'date': d.isoformat(),
            'weekday': d.strftime('%a'),
            'week': (n - 1) // 5 + 1,
            'block': str(ws.cell(r, 5).value or '').strip(),
            'what': str(ws.cell(r, 6).value or '').strip(),
            'pages': pages,
            'range': list(parse_pages(pages) or []),
            'deliverable': str(ws.cell(r, 8).value or '').strip(),
            'minutes': int(ws.cell(r, 9).value or 0),
            'done_xlsx': str(ws.cell(r, 10).value or '').strip().lower() in _YES,
        })

    wb.close()
    today = date.today()
    by_date = next((s for s in sessions if s['date'] >= today.isoformat()), sessions[0] if sessions else None)
    return {
        'start': start.isoformat(),
        'end': sessions[-1]['date'] if sessions else None,
        'total_minutes': sum(s['minutes'] for s in sessions),
        'count': len(sessions),
        'today': by_date['n'] if by_date else None,
        'sessions': sessions,
    }


def _row_for(n: int) -> int:
    return 5 + int(n)


def set_done(n: int, done: bool) -> str:
    """Set column J for session n. Returns a status note ('' when fine)."""
    cfg = config.load()
    path = Path(cfg['workbook'])
    value = 'Yes' if done else None

    wb = openpyxl.load_workbook(path, data_only=False)
    ws = wb['Schedule'] if 'Schedule' in wb.sheetnames else wb.worksheets[0]
    ws.cell(_row_for(n), 10).value = value
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)          # first attempt: in place
    wb.close()
    return ''


def set_done_safe(n: int, done: bool) -> tuple[bool, str]:
    """Write through a temp copy so an open Excel window cannot corrupt the file."""
    cfg = config.load()
    path = Path(cfg['workbook'])
    if not path.exists():
        return False, f'workbook not found: {path}'

    last_err = ''
    for attempt in range(3):
        try:
            return True, set_done(n, done)
        except PermissionError as exc:
            last_err = str(exc)
            # workbook is locked: edit a copy and swap it in
            try:
                tmpdir = Path(tempfile.mkdtemp(prefix='learnloop-'))
                tmp = tmpdir / path.name
                shutil.copy2(path, tmp)
                wb = openpyxl.load_workbook(tmp, data_only=False)
                ws = wb['Schedule'] if 'Schedule' in wb.sheetnames else wb.worksheets[0]
                ws.cell(_row_for(n), 10).value = 'Yes' if done else None
                wb.calculation.fullCalcOnLoad = True
                wb.save(tmp)
                wb.close()
                shutil.move(str(tmp), str(path))
                shutil.rmtree(tmpdir, ignore_errors=True)
                return True, ''
            except Exception as exc2:
                last_err = f'{exc} / retry: {exc2}'
                time.sleep(0.6 * (attempt + 1))
    return False, f'could not write the workbook (close Excel and retry): {last_err}'
