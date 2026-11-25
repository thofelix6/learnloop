"""Configuration for LearnLoop: single JSON file under data/."""
from __future__ import annotations

import json
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

DEFAULTS = {
    'workbook': r'C:\Users\thofe\Downloads\LLM Study Schedule.xlsx',
    'guide': r'C:\Users\thofe\Downloads\Build Your Own LLM - complete guide.pdf',
    'vault': r'C:\Users\thofe\OneDrive\Documents\NeuralBrain',
    'owner_username': '',
    'nas': {
        'lan_url': 'http://192.168.0.137:5005',
        'public_url': 'https://sossonasserver.fnos.net:5005',
        'user': 'None',
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
    return {
        'workbook': cfg.get('workbook'),
        'guide': cfg.get('guide'),
        'vault': cfg.get('vault'),
        'owner_username': cfg.get('owner_username'),
        'nas': nas,
    }
