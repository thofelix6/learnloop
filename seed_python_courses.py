"""Create the two Python courses from the built PDFs and the exercise banks.

Run on the machine holding the material (PC or NAS). Idempotent: re-running updates
the courses, sessions and exercises in place.

Usage:  python seed_python_courses.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, courses, db, pdfsplit  # noqa: E402

db.init()          # the seeder may run before the service ever created the schema
courses.ensure_default_course()

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
GUIDES = config.DATA / 'guides'

SPECS = [
    {
        'slug': 'python-core',
        'title': 'Python Core',
        'subtitle': 'Chapters 1-9 · fundamentals, loops, data structures, functions, strings, exceptions, files',
        'html': ROOT / 'content' / 'core-ch01-03.html',
        'html2': [ROOT / 'content' / 'core-ch04-06.html', ROOT / 'content' / 'core-ch07-09.html'],
        'pdf': GUIDES / 'python-core.pdf',
        'start': date(2026, 11, 23),
        'sessions_per_chapter': 2,
        'exercises': [ROOT / 'content' / 'ex-core-1-4.json', ROOT / 'content' / 'ex-core-5-9.json'],
    },
    {
        'slug': 'python-applied',
        'title': 'Python Applied',
        'subtitle': 'Chapters 10-12 · Turtle graphics, NumPy & Pandas, Matplotlib, face detection',
        'html': ROOT / 'content' / 'applied-ch10-12.html',
        'html2': [],
        'pdf': GUIDES / 'python-applied.pdf',
        'start': date(2026, 12, 21),
        'sessions_per_chapter': 3,
        'exercises': [ROOT / 'content' / 'ex-applied.json'],
    },
]


def chapters_from_html(paths: list[Path]) -> list[tuple[int, str]]:
    out = []
    for p in paths:
        if not p.exists():
            continue
        text = p.read_text(encoding='utf-8')
        for m in re.finditer(r'<h1>\s*Chapter\s+(\d+)\s*[—-]\s*([^<]+?)\s*</h1>', text):
            out.append((int(m.group(1)), m.group(2).strip()))
    return sorted(out)


def chapter_page_map(pdf_path: Path, chapters: list[tuple[int, str]]) -> dict[int, tuple[int, int]]:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        try:
            pages.append((page.extract_text() or '').lower())
        except Exception:
            pages.append('')
    total = len(pages)

    starts: dict[int, int] = {}
    for n, title in chapters:
        words = ' '.join(title.lower().split()[:4])
        hit = None
        for i, text in enumerate(pages):
            flat = ' '.join(text.split())
            if f'chapter {n}' in flat and words and words in flat:
                hit = i + 1
                break
        if hit is None:
            for i, text in enumerate(pages):
                if f'chapter {n}' in ' '.join(text.split()):
                    hit = i + 1
                    break
        starts[n] = hit or 1

    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    ranges = {}
    for idx, (n, start) in enumerate(ordered):
        end = (ordered[idx + 1][1] - 1) if idx + 1 < len(ordered) else total
        ranges[n] = (start, max(start, end))
    return ranges


def weekdays(start: date, count: int) -> list[date]:
    out, cur = [], start
    while len(out) < count:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def build_sessions(chapters, ranges, start: date, per_chapter: int) -> list[dict]:
    total = len(chapters) * per_chapter
    dates = weekdays(start, total)
    sessions = []
    i = 0
    for n, title in chapters:
        lo, hi = ranges.get(n, (1, 1))
        for k in range(per_chapter):
            kind = 'Study' if k == 0 else ('Practice' if k == 1 else 'Apply')
            if per_chapter >= 3 and k == 2:
                kind = 'Project'
            if kind == 'Study':
                what = f'Read chapter {n} (pages {lo}-{hi}). Retype every example rather than reading it passively.'
                deliverable = f'Your own notes on chapter {n}, with the examples working'
                minutes = 60
            elif kind == 'Practice':
                what = f'Do exercises ex-{n}-1 to ex-{n}-3 on the site until every test passes.'
                deliverable = 'All chapter exercises passing'
                minutes = 45
            else:
                what = f'Build the small project from chapter {n} and push it to the NAS.'
                deliverable = 'A working script you wrote yourself'
                minutes = 60
            sessions.append({
                'n': i + 1,
                'date': dates[i].isoformat(),
                'weekday': dates[i].strftime('%a'),
                'week': i // 5 + 1,
                'block': f'Chapter {n} - {title} ({kind})',
                'what': what,
                'pages': f'{lo}-{hi}',
                'deliverable': deliverable,
                'minutes': minutes,
            })
            i += 1
    return sessions


def main() -> int:
    GUIDES.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        pdf = spec['pdf']
        if not pdf.exists():
            print(f'! missing {pdf} - build it first')
            continue
        chapters = chapters_from_html([spec['html'], *spec['html2']])
        if not chapters:
            print(f'! no chapters found in {spec["html"].name}')
            continue
        ranges = chapter_page_map(pdf, chapters)
        sessions = build_sessions(chapters, ranges, spec['start'], spec['sessions_per_chapter'])

        cid = db.upsert_course(spec['slug'], spec['title'], spec['subtitle'], kind='json',
                               guide=str(pdf), position=2 if spec['slug'] == 'python-core' else 3)
        db.set_course_sessions(cid, sessions)
        print(f'{spec["slug"]}: {len(chapters)} chapters, {len(sessions)} sessions, '
              f'pages {ranges}')

        split = pdfsplit.split_generic(pdf, sessions, courses.sessions_dir(spec['slug']), force=True)
        print(f'   split: {len(split["written"])} PDFs, {len(split["zips"])} weekly zips')

        count = 0
        for bank in spec['exercises']:
            if not bank.exists():
                print(f'   ! missing {bank.name}')
                continue
            for idx, ex in enumerate(json.loads(bank.read_text(encoding='utf-8'))):
                db.upsert_exercise(
                    cid, int(ex['chapter']), ex['slug'], ex['title'], ex['prompt'],
                    ex.get('starter', ''), json.dumps(ex['tests']), ex.get('solution', ''),
                    json.dumps(ex.get('hints', [])), ex.get('difficulty', 'medium'), idx)
                count += 1
        print(f'   exercises: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
