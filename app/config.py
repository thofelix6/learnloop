"""Configuration for LearnLoop: single JSON file under data/."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / 'data'
STATIC = BASE / 'static'
SESSIONS_DIR = DATA / 'sessions'
CONFIG_PATH = DATA / 'config.json'
DB_PATH = DATA / 'learnloop.db'

for _d in (DATA, SESSIONS_DIR, STATIC):
    _d.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

# Nothing machine-specific belongs in these defaults: this file ships publicly and
# the real paths live in data/config.json (0600, never committed).
DEFAULTS = {
    'workbook': '',
    'guide': '',
    'vault': '',
    'owner_username': '',
    'site': {
        'name': 'LearnLoop',
        'tagline': 'Planned study sessions, split PDFs, narrated lectures and auto-graded exercises.',
        'public_url': '',            # e.g. https://learnloop.example.ts.net
        'contact_email': '',         # shown on the privacy and terms pages
        'effective_date': '',        # ISO date shown on those pages
        'operator': '',              # who runs this instance
        'jurisdiction': '',
    },
    'nas': {
        'lan_url': '',
        'public_url': '',
        'user': '',
        'password_enc': '',          # DPAPI blob, base64; never plaintext on disk
        'remote_dir': '/AI_course/Build Your Own LLM',
        'active': 'lan',
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    with _lock:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2), encoding='utf-8')
            return json.loads(json.dumps(DEFAULTS))
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            raw = {}
        cfg = _merge(DEFAULTS, raw)
        # an environment variable wins so the public origin can differ per host
        env_url = (os.environ.get('LEARNLOOP_PUBLIC_URL') or '').strip()
        if env_url:
            cfg.setdefault('site', {})['public_url'] = env_url
        return cfg


def save(cfg: dict) -> None:
    with _lock:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding='utf-8')


def update(patch: dict) -> dict:
    cfg = load()
    cfg = _merge(cfg, patch)
    save(cfg)
    return cfg


def public_view(cfg: dict) -> dict:
    """Config without secrets, for the browser."""
    nas = dict(cfg.get('nas') or {})
    nas.pop('password_enc', None)
    nas['has_password'] = bool((cfg.get('nas') or {}).get('password_enc'))
    site = dict(cfg.get('site') or {})
    return {
        'workbook': cfg.get('workbook'),
        'guide': cfg.get('guide'),
        'vault': cfg.get('vault'),
        'owner_username': cfg.get('owner_username'),
        'site': site,
        'nas': nas,
    }
