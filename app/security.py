"""Password hashing, session tokens, and DPAPI secret storage."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import secrets
from ctypes import wintypes

# scrypt parameters: ~16 MB, a few ms per hash
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return base64.b64encode(dk).decode(), base64.b64encode(salt).decode()


def verify_password(password: str, pw_hash: str, pw_salt: str) -> bool:
    try:
        salt = base64.b64decode(pw_salt)
        expected = base64.b64decode(pw_hash)
        dk = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=_N, r=_R, p=_P, dklen=32)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


# ------------------------------------------------------------------ DPAPI
# Windows-only: the NAS password is encrypted per Windows user. On Linux (the NAS
# deployment) there is no DPAPI, so the password comes from the environment
# (LEARNLOOP_NAS_PASSWORD via a 0600 EnvironmentFile) and this module degrades
# gracefully instead of failing at import time.
import os as _os

_IS_WINDOWS = _os.name == 'nt'

if _IS_WINDOWS:
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def _in_blob(data: bytes):
        buf = ctypes.create_string_buffer(data, len(data))
        blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        return blob, buf


def dpapi_encrypt(text: str) -> str:
    """Encrypt with the current Windows user's DPAPI key. Windows only."""
    if not _IS_WINDOWS:
        raise RuntimeError('DPAPI is only available on Windows; use LEARNLOOP_NAS_PASSWORD')
    data = text.encode('utf-8')
    blob_in, _keep = _in_blob(data)
    blob_out = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None,
                                   _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError(f'CryptProtectData failed: {ctypes.get_last_error()}')
    try:
        raw = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)
    return base64.b64encode(raw).decode()


def dpapi_decrypt(b64: str) -> str:
    if not b64:
        return ''
    if not _IS_WINDOWS:
        return ''
    raw = base64.b64decode(b64)
    blob_in, _keep = _in_blob(raw)
    blob_out = _DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None,
                                     _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError(f'CryptUnprotectData failed: {ctypes.get_last_error()}')
    try:
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)
    return out.decode('utf-8')

