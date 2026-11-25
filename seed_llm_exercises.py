"""Add the Build Your Own LLM book exercises (written, with the book's answers) to that course."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import db  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BANK = Path(__file__).resolve().parent / 'content' / 'llm-exercises.json'


def main() -> int:
    db.init()
    course = db.get_course('build-llm')
    if not course:
        print('course build-llm missing')
        return 1
    cid = int(course['id'])

    bank = json.loads(BANK.read_text(encoding='utf-8'))
    for i, ex in enumerate(bank):
        db.upsert_exercise(
            cid, int(ex['chapter']), ex['slug'], ex['title'], ex['prompt'],
            ex.get('starter', ''), json.dumps(ex.get('tests') or []), ex.get('solution', ''),
            json.dumps(ex.get('hints') or []), ex.get('difficulty', 'medium'),
            i, kind=ex.get('kind', 'code'), answer=ex.get('answer', ''))
    print(f'seeded {len(bank)} written exercises into build-llm (id {cid})')

    rows = db.list_exercises(cid)
    print(f'course now has {len(rows)} exercises; kinds:',
          {r['kind']: sum(1 for x in rows if x['kind'] == r['kind']) for r in rows})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
