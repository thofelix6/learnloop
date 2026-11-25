"""Minimal WebDAV client for the fnOS NAS (stdlib only)."""
from __future__ import annotations

import base64
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from . import config, security

DAV_NS = '{DAV:}'
TIMEOUT = 20


class NasError(RuntimeError):
    pass


class WebDav:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip('/')
        self.user = user or ''
        self.password = password or ''

    # ---------------------------------------------------------------- plumbing
    def _auth_header(self) -> dict:
        if not self.user and not self.password:
            return {}
        raw = f'{self.user}:{self.password}'.encode('utf-8')
        return {'Authorization': 'Basic ' + base64.b64encode(raw).decode('ascii')}

    def url(self, path: str) -> str:
        path = '/' + path.lstrip('/')
        quoted = '/'.join(urllib.parse.quote(seg) for seg in path.split('/'))
        return self.base + quoted

    def _request(self, method: str, path: str, data: bytes | None = None,
                 headers: dict | None = None):
        req = urllib.request.Request(self.url(path), data=data, method=method)
        for k, v in self._auth_header().items():
            req.add_header(k, v)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            body = b''
            try:
                body = exc.read()[:400]
            except Exception:
                pass
            raise NasError(f'{method} {path} -> HTTP {exc.code} {exc.reason} {body[:200]!r}') from exc
        except Exception as exc:
            raise NasError(f'{method} {path} -> {exc}') from exc

    # ------------------------------------------------------------------- api
    def test(self) -> dict:
        try:
            resp = self._request('OPTIONS', '/')
            return {'ok': True, 'status': resp.status,
                    'dav': resp.headers.get('DAV'), 'url': self.base}
        except NasError as exc:
            return {'ok': False, 'error': str(exc), 'url': self.base}

    def list(self, path: str) -> list[dict]:
        body = (b'<?xml version="1.0" encoding="utf-8"?>'
                b'<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/><d:resourcetype/>'
                b'<d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>')
        resp = self._request('PROPFIND', path, data=body,
                             headers={'Depth': '1', 'Content-Type': 'application/xml'})
        raw = resp.read()
        out = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise NasError(f'could not parse PROPFIND XML: {exc}') from exc
        for node in root.iter(f'{DAV_NS}response'):
            href = node.find(f'{DAV_NS}href')
            if href is None or not href.text:
                continue
            name = urllib.parse.unquote(href.text.rstrip('/').split('/')[-1])
            is_dir = node.find(f'.//{DAV_NS}collection') is not None
            size_el = node.find(f'.//{DAV_NS}getcontentlength')
            mod_el = node.find(f'.//{DAV_NS}getlastmodified')
            out.append({
                'name': name,
                'href': href.text,
                'is_dir': is_dir,
                'size': int(size_el.text) if size_el is not None and size_el.text else None,
                'modified': mod_el.text if mod_el is not None else None,
            })
        return out

    def mkdirs(self, path: str) -> None:
        parts = [p for p in path.strip('/').split('/') if p]
        for i in range(1, len(parts) + 1):
            sub = '/' + '/'.join(parts[:i])
            try:
                self._request('MKCOL', sub)
            except NasError as exc:
                msg = str(exc)
                if 'HTTP 405' in msg or 'HTTP 301' in msg or 'HTTP 409' in msg:
                    continue          # already exists
                raise

    def put(self, local: Path, remote_path: str) -> dict:
        data = Path(local).read_bytes()
        resp = self._request('PUT', remote_path, data=data,
                             headers={'Content-Type': 'application/pdf',
                                      'Overwrite': 'T'})
        return {'path': remote_path, 'bytes': len(data), 'status': resp.status}

    def exists(self, remote_path: str) -> bool:
        try:
            self._request('HEAD', remote_path)
            return True
        except NasError:
            return False


def client(url_key: str | None = None) -> WebDav:
    cfg = config.load()
    nas = cfg.get('nas') or {}
    key = url_key or nas.get('active') or 'lan'
    base = nas.get('public_url') if key == 'public' else nas.get('lan_url')
    # Linux (NAS deployment) has no DPAPI: take the password from the environment,
    # supplied by a 0600 systemd EnvironmentFile.
    import os
    password = os.environ.get('LEARNLOOP_NAS_PASSWORD', '')
    if not password and nas.get('password_enc'):
        try:
            password = security.dpapi_decrypt(nas['password_enc'])
        except Exception:
            password = ''
    return WebDav(base or '', nas.get('user') or '', password)


def remote_dir() -> str:
    cfg = config.load()
    return (cfg.get('nas') or {}).get('remote_dir') or '/AI_course/Build Your Own LLM'


def upload_session_file(n: int, url_key: str | None = None, directory=None,
                        slug: str = 'build-llm') -> dict:
    from . import pdfsplit
    f = pdfsplit.file_for(n, directory) if directory else pdfsplit.session_file(n)
    if not f:
        raise NasError(f'session {n} has no split PDF yet - run the splitter first')
    dav = client(url_key)
    target_dir = remote_dir() if slug == 'build-llm' else f'{remote_dir()}/{slug}'
    dav.mkdirs(target_dir)
    result = dav.put(f, f'{target_dir}/{f.name}')
    result['file'] = f.name
    return result


def upload_week_zip(week: int, url_key: str | None = None) -> dict:
    from . import pdfsplit
    zp = pdfsplit.week_zip(week)
    if not zp:
        raise NasError(f'no zip for week {week} - run the splitter first')
    dav = client(url_key)
    target_dir = f'{remote_dir()}/Weekly bundles'
    dav.mkdirs(target_dir)
    result = dav.put(zp, f'{target_dir}/{zp.name}')
    result['file'] = zp.name
    return result


def status(url_key: str | None = None) -> dict:
    dav = client(url_key)
    info = dav.test()
    info['remote_dir'] = remote_dir()
    if info.get('ok'):
        try:
            entries = dav.list(remote_dir())
            info['remote_files'] = [
                {'name': e['name'], 'size': e['size'], 'is_dir': e['is_dir']}
                for e in entries if e['name']]
        except NasError as exc:
            info['remote_files'] = []
            info['listing_error'] = str(exc)
    return info
