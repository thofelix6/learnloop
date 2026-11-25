"""Site-wide concerns: HTTPS, security headers, static caching, SEO files, 404.

Registered from ``app.main`` with :func:`install`. Everything here is transport or
metadata, so it never touches the learning features themselves.
"""
from __future__ import annotations

import ipaddress
import mimetypes
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from . import config

# Windows' mimetypes database has no entry for woff2, so StaticFiles would serve the
# fonts as application/octet-stream and browsers would ignore <link rel=preload as=font>.
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('image/webp', '.webp')

STATIC = config.STATIC

# Pages that answer with a file instead of the SPA shell.
DOC_PAGES = {
    '/privacy': 'privacy.html',
    '/terms': 'terms.html',
}

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Frame-Options': 'DENY',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
}

# The app is a single document with no inline <script>; inline style attributes are
# used throughout the markup, so styles allow 'unsafe-inline' while scripts do not.
CSP = (
    "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; "
    "object-src 'none'; img-src 'self' data: blob:; media-src 'self' blob:; "
    "font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "worker-src 'self' blob:; connect-src 'self'"
)

_HSTS = 'max-age=31536000'

_IPV4_IN_URL = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')


def configured_public_url() -> str:
    """The canonical public origin, without a trailing slash."""
    site = (config.load().get('site') or {})
    url = str(site.get('public_url') or '').strip()
    if not url:
        url = str(__import__('os').environ.get('LEARNLOOP_PUBLIC_URL') or '').strip()
    return url.rstrip('/')


def is_https(request: Request) -> bool:
    if request.url.scheme == 'https':
        return True
    if (request.headers.get('x-forwarded-proto') or '').lower().startswith('https'):
        return True
    # Tailscale Funnel always reaches us over its own TLS terminator.
    return bool(request.headers.get('tailscale-funnel-request'))


def _is_public_host(host_header: str) -> bool:
    """True when redirecting this host to HTTPS cannot loop or strand a LAN user.

    The NAS is also reached over plain HTTP on the LAN (Coolify's Traefik, sslip.io
    names that resolve to a private address), where no certificate exists. Those
    requests are served as-is; HSTS still upgrades browsers that have seen HTTPS.
    """
    host = (host_header or '').split(',')[0].strip()
    host = host.split(':')[0].strip('[]').lower()
    if not host:
        return False
    if host in ('localhost', '127.0.0.1', '::1'):
        return False
    if host.endswith('.local') or host.endswith('.sslip.io') or host.endswith('.ts.net.private'):
        return False
    if host.endswith('.ts.net'):
        return True
    if _IPV4_IN_URL.match(host):
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return False
    if ':' in host:                       # bare IPv6 literal
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return False
    return True


def _cache_control(path: str) -> str | None:
    if path.startswith('/api/'):
        return 'no-store'
    if path.startswith('/static/vendor/'):
        return 'public, max-age=31536000, immutable'
    if path.startswith('/static/'):
        # Filenames carry no content hash, so every request revalidates (ETag -> 304).
        # Pages reference them with ?v=<asset version> as well; the belt and braces
        # matter because a stale script against fresh HTML is how a deploy half-applies.
        return 'no-cache'
    if path in ('/', '/privacy', '/terms') or path.endswith('.html'):
        return 'no-cache'
    if path in ('/sw.js', '/manifest.webmanifest', '/robots.txt', '/sitemap.xml'):
        return 'no-cache'
    return None


def asset_version() -> str:
    """A stamp that changes whenever the app shell changes, for ?v= on asset URLs."""
    stamp = 0
    for name in ('app.js', 'style.css', 'sw.js'):
        try:
            stat = (STATIC / name).stat()
        except OSError:
            continue
        stamp = max(stamp, int(stat.st_mtime), stat.st_size)
    return str(stamp or 1)


def _public_base(request: Request) -> str:
    base = configured_public_url()
    if base:
        return base
    scheme = 'https' if is_https(request) else 'http'
    return f'{scheme}://{request.headers.get("host") or request.url.netloc}'


# --------------------------------------------------------------------- routes
def _robots(request: Request) -> PlainTextResponse:
    base = _public_base(request)
    body = (
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /api/\n'
        'Disallow: /admin\n'
        'Disallow: /settings\n'
        f'\nSitemap: {base}/sitemap.xml\n'
    )
    return PlainTextResponse(body, headers={'Cache-Control': 'no-cache'})


def _sitemap(request: Request) -> Response:
    base = _public_base(request)
    today = datetime.now(timezone.utc).date().isoformat()
    urls = [
        (f'{base}/', '1.0', 'weekly'),
        (f'{base}/privacy', '0.3', 'yearly'),
        (f'{base}/terms', '0.3', 'yearly'),
    ]
    entries = ''.join(
        f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n'
        f'    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>\n'
        for loc, prio, freq in urls
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f'{entries}</urlset>\n')
    return Response(xml, media_type='application/xml',
                    headers={'Cache-Control': 'no-cache'})


def render_page(name: str, request: Request | None = None, status_code: int = 200) -> HTMLResponse:
    """Serve a static document with the instance's own site facts filled in.

    Tokens keep the HTML readable while letting every deployment state its real
    name, origin, contact address and effective date.
    """
    cfg = config.load()
    info = cfg.get('site') or {}
    today = datetime.now(timezone.utc).date().isoformat()
    if request is not None:
        base = _public_base(request)
    else:
        base = configured_public_url()
    email = str(info.get('contact_email') or '').strip()
    contact = (f'<a href="mailto:{escape(email)}">{escape(email)}</a>' if email
               else 'the administrator who approved your account')
    operator = str(info.get('operator') or '').strip() or 'the administrator of this instance'
    tokens = {
        '{{SITE_NAME}}': info.get('name') or 'LearnLoop',
        '{{TAGLINE}}': info.get('tagline') or '',
        '{{BASE}}': base,
        '{{PUBLIC_URL}}': base,
        '{{PUBLIC_HOST}}': urlsplit(base).hostname or 'this site',
        '{{EFFECTIVE_DATE}}': info.get('effective_date') or today,
        '{{OPERATOR}}': operator,
        '{{JURISDICTION}}': str(info.get('jurisdiction') or '').strip(),
        '{{ASSET_V}}': asset_version(),
        '{{YEAR}}': str(datetime.now(timezone.utc).year),
    }
    text = (STATIC / name).read_text(encoding='utf-8')
    for key, value in tokens.items():
        text = text.replace(key, escape(str(value)))
    jurisdiction = str(info.get('jurisdiction') or '').strip()
    text = text.replace('{{JURISDICTION_CLAUSE}}', f' ({escape(jurisdiction)})' if jurisdiction else '')
    text = text.replace('{{CONTACT}}', contact)
    return HTMLResponse(text, status_code=status_code, headers={'Cache-Control': 'no-cache'})


def _doc_page(name: str, request: Request | None = None) -> HTMLResponse:
    return render_page(name, request)


def install(app: FastAPI) -> None:
    """Register middleware, SEO routes, and the HTML 404 handler."""

    @app.middleware('http')
    async def _site_middleware(request: Request, call_next):
        # 1. Enforce HTTPS for names that can actually present a certificate.
        if (request.headers.get('x-forwarded-proto') or '').lower() == 'http' \
                and _is_public_host(request.headers.get('host', '')):
            target = request.url.replace(scheme='https')
            return RedirectResponse(str(target), status_code=308)

        response = await call_next(request)

        # 2. Security headers on everything, HSTS only once TLS is in play.
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault('Content-Security-Policy', CSP)
        if is_https(request):
            response.headers.setdefault('Strict-Transport-Security', _HSTS)

        # 3. Caching policy: immutable vendored assets, short-lived app assets,
        #    never-cached HTML and API responses.
        cache = _cache_control(request.url.path)
        if cache and 'cache-control' not in {k.lower() for k in response.headers.keys()}:
            response.headers['Cache-Control'] = cache
        if request.url.path.startswith('/api/'):
            response.headers.setdefault('X-Robots-Tag', 'noindex')
        return response

    @app.get('/robots.txt', include_in_schema=False)
    def robots(request: Request):
        return _robots(request)

    @app.get('/sitemap.xml', include_in_schema=False)
    def sitemap(request: Request):
        return _sitemap(request)

    def make_doc_handler(filename: str):
        def handler(request: Request):
            return _doc_page(filename, request)
        return handler

    for route, filename in DOC_PAGES.items():
        app.add_api_route(route, make_doc_handler(filename), methods=['GET'],
                          include_in_schema=False)

    @app.get('/favicon.ico', include_in_schema=False)
    def favicon():
        return FileResponse(str(STATIC / 'favicon.ico'), media_type='image/x-icon',
                            headers={'Cache-Control': 'public, max-age=86400'})

    @app.get('/fresh', include_in_schema=False)
    def fresh():
        """Clear this origin's HTTP cache and browser storage, then offer the app.

        A browser can hold an old document from before the app sent cache headers at
        all; no response header can reach that entry. Loading this URL is a different
        request, so it is always fetched, and ``Clear-Site-Data`` empties the cache and
        the service-worker storage behind it. Cookies are deliberately left alone, so
        the visitor stays signed in.
        """
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Cache cleared · LearnLoop</title>'
            '<link rel="icon" href="/static/icon.svg" type="image/svg+xml">'
            '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;'
            'background:#0a0d12;color:#e8eef6;font:16px/1.6 "Segoe UI",system-ui,sans-serif}'
            'div{max-width:520px;padding:28px;border:1px solid #22303f;border-radius:16px;'
            'background:#131a24}h1{font-size:22px;margin:0 0 10px}'
            'p{color:#8fa1b5;margin:0 0 18px}a{display:inline-block;padding:11px 18px;'
            'border-radius:10px;background:#3fd0e0;color:#06121a;font-weight:650;'
            'text-decoration:none}</style>'
            '<div><h1>Cache cleared</h1>'
            '<p>This browser dropped the old copy of LearnLoop. Open the app to load the '
            'current version.</p><a href="/">Open LearnLoop</a></div></html>'
        )
        return HTMLResponse(page, headers={
            'Clear-Site-Data': '"cache", "storage"',
            'Cache-Control': 'no-store',
        })

    @app.exception_handler(404)
    async def _not_found(request: Request, exc):
        if request.url.path.startswith('/api/'):
            detail = getattr(exc, 'detail', 'not found')
            return JSONResponse({'detail': detail}, status_code=404)
        if not (STATIC / '404.html').is_file():
            return HTMLResponse('<h1>404</h1><p>Not found.</p>', status_code=404)
        return render_page('404.html', request, status_code=404)
