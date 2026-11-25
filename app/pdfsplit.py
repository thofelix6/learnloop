"""Split a guide PDF into one file per study session, plus weekly bundles."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from . import config

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str, limit: int = 60) -> str:
    cleaned = _BAD.sub('-', text or '').strip(' .-')
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return (cleaned[:limit].rstrip(' .-') or 'session')


def session_filename(s: dict) -> str:
    pages = s.get('pages') or ''
    base = f"S{int(s['n']):02d} - {safe_name(s['block'])}"
    return f'{base} - p{pages}.pdf' if pages else f'{base}.pdf'


def file_for(n: int, directory: Path | None = None) -> Path | None:
    directory = Path(directory) if directory else config.SESSIONS_DIR
    hits = sorted(directory.glob(f'S{int(n):02d} - *.pdf'))
    return hits[0] if hits else None


def week_zip(week: int, directory: Path | None = None) -> Path | None:
    directory = Path(directory) if directory else config.DATA / 'zips'
    hits = sorted(directory.glob(f'Week {int(week):02d} - *.zip'))
    return hits[0] if hits else None


def split_generic(guide: Path, sessions: list[dict], out_dir: Path, force: bool = False) -> dict:
    """Cut `guide` into per-session PDFs according to each session's page range."""
    guide = Path(guide)
    if not guide.exists():
        raise FileNotFoundError(f'guide not found: {guide}')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(guide))
    total_pages = len(reader.pages)

    written, skipped, errors = [], [], []
    for s in sessions:
        rng = s.get('range') or []
        if len(rng) != 2:
            # tolerate callers that only supply a page string like "8-10"
            from .plan import parse_pages
            parsed = parse_pages(s.get('pages') or '')
            rng = list(parsed) if parsed else []
        if len(rng) != 2:
            errors.append(f"session {s.get('n')}: bad page range {s.get('pages')!r}")
            continue
        lo, hi = int(rng[0]), int(rng[1])
        lo = max(1, min(lo, total_pages))
        hi = max(lo, min(hi, total_pages))

        target = out_dir / session_filename(s)
        if target.exists() and not force:
            skipped.append(target.name)
            continue
        writer = PdfWriter()
        for p in range(lo - 1, hi):
            writer.add_page(reader.pages[p])
        writer.add_metadata({
            '/Title': f"Session {s.get('n')} - {s.get('block', '')}",
            '/Subject': s.get('what', ''),
            '/Keywords': f"pages {lo}-{hi}; week {s.get('week')}; {s.get('deliverable', '')}",
        })
        with open(target, 'wb') as fh:
            writer.write(fh)
        written.append(target.name)

    # weekly bundles
    zip_dir = out_dir.parent / f'{out_dir.name}-zips'
    zip_dir.mkdir(parents=True, exist_ok=True)
    by_week: dict[int, list[dict]] = {}
    for s in sessions:
        by_week.setdefault(int(s.get('week') or 1), []).append(s)
    zips = []
    for week, items in sorted(by_week.items()):
        zp = zip_dir / f"Week {week:02d} - sessions {items[0]['n']:02d}-{items[-1]['n']:02d}.zip"
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for s in items:
                f = out_dir / session_filename(s)
                if f.exists():
                    zf.write(f, arcname=f.name)
        zips.append(zp.name)

    return {
        'pages_in_guide': total_pages,
        'written': written,
        'skipped': skipped,
        'errors': errors,
        'zips': zips,
        'out_dir': str(out_dir),
    }


# --- legacy single-course entry point kept for the original PDFs ------------
def split(force: bool = False) -> dict:
    from . import plan
    data = plan.read_plan()
    return split_generic(Path(config.load()['guide']), data['sessions'],
                         config.SESSIONS_DIR, force=force)


def session_file(n: int) -> Path | None:
    return file_for(n, config.SESSIONS_DIR)
