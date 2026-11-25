"""Validate an exercise bank: every solution must pass every test."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def check(path: Path) -> tuple[int, int, list[str]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        return 0, 0, [f'{path.name}: not a JSON array']
    problems = []
    total_tests = 0
    seen = set()
    for ex in data:
        slug = ex.get('slug', '?')
        for key in ('slug', 'chapter', 'title', 'prompt', 'starter', 'tests', 'solution', 'hints', 'difficulty'):
            if key not in ex:
                problems.append(f'{slug}: missing {key}')
        if slug in seen:
            problems.append(f'{slug}: duplicate slug')
        seen.add(slug)
        tests = ex.get('tests') or []
        total_tests += len(tests)
        if not tests:
            problems.append(f'{slug}: no tests')
            continue
        namespace = {}
        try:
            exec(compile(ex['solution'], f'{slug}/solution', 'exec'), namespace)
        except Exception as exc:
            problems.append(f'{slug}: solution failed to load: {type(exc).__name__}: {exc}')
            continue
        for i, test in enumerate(tests):
            if 'name' not in test or 'code' not in test:
                problems.append(f'{slug}: test {i} missing name/code')
                continue
            try:
                exec(compile(test['code'], f'{slug}/test{i}', 'exec'), dict(namespace))
            except Exception as exc:
                problems.append(f'{slug}/{test.get("name", i)}: {type(exc).__name__}: {exc}')
    return len(data), total_tests, problems


if __name__ == '__main__':
    files = [Path(p) for p in sys.argv[1:]] or sorted((ROOT / 'content').glob('*.json'))
    grand_ok = True
    for f in files:
        n, t, problems = check(f)
        status = 'OK' if not problems else f'{len(problems)} PROBLEM(S)'
        print(f'{f.name:28} {n:3} exercises  {t:3} tests   {status}')
        for p in problems[:12]:
            print('    -', p)
        if problems:
            grand_ok = False
    raise SystemExit(0 if grand_ok else 1)
