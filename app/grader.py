"""Sandboxed execution of learner code for auto-graded exercises.

Design notes
------------
* Each submission runs in its own temporary directory as a subprocess of the app's
  own interpreter, with `-I` (isolated: no PYTHONPATH, no user site-packages).
* Resource limits: CPU seconds, address space, file size, no core dumps.
* Hard wall-clock timeout on top of the CPU limit, so an infinite loop cannot
  wedge the worker.
* The harness imports the learner's file as a module, then executes each test
  string with that module's namespace, reporting pass/fail per test.

The code runs on the NAS as the app user. Only approved accounts can submit, and
`LEARNLOOP_ALLOW_CODE=0` in the environment disables the runner entirely.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = '''
import json, sys, importlib.util

code_path, tests_path = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("solution", code_path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except BaseException as exc:
    print(json.dumps({"module_error": f"{type(exc).__name__}: {exc}"}))
    sys.exit(0)

with open(tests_path, encoding="utf-8") as fh:
    tests = json.load(fh)

results = []
for test in tests:
    namespace = dict(vars(mod))
    try:
        exec(test["code"], namespace)
        results.append({"name": test["name"], "ok": True})
    except BaseException as exc:
        message = "assertion failed" if isinstance(exc, AssertionError) else f"{type(exc).__name__}: {exc}"
        results.append({"name": test["name"], "ok": False, "error": message[:300]})
print(json.dumps({"results": results}))
'''

MAX_TIMEOUT = 12


def _limits():
    """Runs in the child before exec: cap CPU, memory, file size, no core dumps."""
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def enabled() -> bool:
    return os.environ.get('LEARNLOOP_ALLOW_CODE', '1') != '0'


def run(code: str, tests: list[dict], timeout: int = MAX_TIMEOUT) -> dict:
    """Execute learner code against tests. Never raises for bad code."""
    if not enabled():
        return {'ok': False, 'disabled': True,
                'module_error': 'code execution is disabled on this server', 'results': []}
    if not code or not code.strip():
        return {'ok': False, 'module_error': 'no code submitted', 'results': []}

    timeout = max(2, min(int(timeout or MAX_TIMEOUT), MAX_TIMEOUT))
    with tempfile.TemporaryDirectory(prefix='learnloop-grade-') as td:
        root = Path(td)
        code_path = root / 'solution.py'
        tests_path = root / 'tests.json'
        harness_path = root / 'harness.py'
        code_path.write_text(code, encoding='utf-8')
        tests_path.write_text(json.dumps(tests), encoding='utf-8')
        harness_path.write_text(HARNESS, encoding='utf-8')

        env = {
            'PATH': '/usr/local/bin:/usr/bin:/bin',
            'HOME': td,
            'TMPDIR': td,
            'LANG': 'C.UTF-8',
            'PYTHONIOENCODING': 'utf-8',
        }
        cmd = [sys.executable, '-I', str(harness_path), str(code_path), str(tests_path)]
        try:
            proc = subprocess.run(
                cmd, cwd=td, env=env, timeout=timeout, capture_output=True,
                preexec_fn=_limits if os.name == 'posix' else None)
        except subprocess.TimeoutExpired:
            return {'ok': False, 'module_error': f'timeout after {timeout}s (infinite loop?)', 'results': []}
        except Exception as exc:                      # pragma: no cover - defensive
            return {'ok': False, 'module_error': f'runner error: {exc}', 'results': []}

        stdout = (proc.stdout or b'').decode('utf-8', 'replace').strip()
        stderr = (proc.stderr or b'').decode('utf-8', 'replace').strip()

        payload = None
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if payload is None:
            # crashed before printing: usually a syntax error or a hard kill
            reason = stderr.splitlines()[-1] if stderr else f'exited with code {proc.returncode}'
            return {'ok': False, 'module_error': reason[:300], 'results': [], 'stderr': stderr[-600:]}

        if payload.get('module_error'):
            return {'ok': False, 'module_error': payload['module_error'][:300],
                    'results': [], 'stderr': stderr[-600:]}

        results = payload.get('results', [])
        passed = all(r.get('ok') for r in results) and bool(results)
        return {'ok': passed, 'module_error': None, 'results': results,
                'passed_count': sum(1 for r in results if r.get('ok')),
                'total': len(results), 'stderr': stderr[-600:] if stderr else ''}
