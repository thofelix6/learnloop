# LearnLoop

A small, self-hosted study app: a workbook becomes a dated plan of sessions, each with a split
PDF or styled reader text, an optional narrated lecture, a timer, notes, and exercises that are
graded on the server.

Built for one book (*Build Your Own LLM*) and a handful of courses, running FastAPI + SQLite with
vanilla JS on the front end. No build step, no CDN, no bundler.

## Run it

```bash
pip install fastapi "uvicorn[standard]" pypdf openpyxl
python -m uvicorn app.main:app --host 0.0.0.0 --port 7777
```

Open <http://127.0.0.1:7777>. The first visit creates the administrator account.

`data/config.json` holds the workbook, guide PDF and notes folder for each course. Paths are
machine-specific, so they live in that file (mode 0600, never committed) — not in `app/config.py`.

## What is in here

| Area | Notes |
|---|---|
| `app/main.py` | HTTP surface: auth, plan, sessions, exercises, NAS sync, admin, analytics |
| `app/site.py` | Security headers and CSP, HTTPS enforcement, robots.txt, sitemap.xml, legal pages, 404 |
| `app/db.py` | SQLite schema and queries, including the aggregate `pageviews` counter |
| `app/grader.py` | Runs submitted code in a separate process with CPU/memory limits |
| `static/` | Single-page app, styles, icons, service worker, legal pages |
| `tools/` | Rebuildable assets: brand images and the palette contrast audit |

## Site, legal pages and SEO

`data/config.json` → `site`:

```json
"site": {
  "name": "LearnLoop",
  "public_url": "https://learnloop.example.ts.net",
  "contact_email": "admin@example.com",
  "effective_date": "2026-11-25",
  "operator": "who runs this instance",
  "jurisdiction": "optional"
}
```

These values are substituted into `/privacy` and `/terms`, the canonical URL, the Open Graph
tags, `sitemap.xml` and `robots.txt`. They can also be edited in **Settings** (admins only).
`LEARNLOOP_PUBLIC_URL` overrides `public_url` per host.

- `GET /privacy`, `GET /terms` — server-rendered documents, no JavaScript, indexable.
- `GET /robots.txt`, `GET /sitemap.xml` — generated from `public_url`.
- Unknown paths return a styled 404 with status 404; unknown `/api/` paths return JSON.

## Analytics

First-party and cookieless. The app sends one `POST /api/hit` beacon per view **only when the
visitor allows it** in the consent banner; the server stores the path, the day and (if any) the
referring hostname. No IP address, no user agent, no identifier, no third-party script.
Admins see the totals in **Admin → Traffic** (`GET /api/analytics`).

## Security

- Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` on HTTPS, 30-day expiry.
- CSP (no inline scripts), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, HSTS on HTTPS.
- HTTP is redirected to HTTPS for public hostnames; LAN hostnames without a certificate are served
  as-is so local access keeps working.
- Sign-in: scrypt hashes, 8 attempts per IP per 10 minutes. Sign-up: honeypot field, a minimum
  form dwell time, 5 requests per IP per hour, admin approval.
- No secret ever reaches the browser: `/api/config` is admin-only and strips the NAS password.

## Assets

```bash
python tools/make_brand_assets.py    # favicon.ico, icon-192/512, apple-touch-icon, og.jpg
python tools/contrast_audit.py       # WCAG contrast for the palette
```

## Deploying

The production instance runs on the home NAS as `learnloop.service` (uvicorn on port 7777),
published through a TLS tunnel. Deploy by extracting the changed files over
`/mnt/data/1000/learnloop` and restarting the unit; `data/` is never part of a deploy.
