"""Assemble the course HTML fragments into a styled book and print it to PDF.

Usage:  python build_pdf.py core
        python build_pdf.py applied
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'build'

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", "Noto Sans", sans-serif;
  font-size: 10.5pt; line-height: 1.55; color: #1b2430; margin: 0;
}
h1 { font-size: 21pt; line-height: 1.2; margin: 0 0 6pt; color: #0f1b2a; }
h2 { font-size: 12.5pt; margin: 16pt 0 5pt; color: #12304d; }
p { margin: 0 0 8pt; }
ul, ol { margin: 0 0 9pt 18pt; }
li { margin-bottom: 3pt; }
code { font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt;
       background: #eef2f7; padding: 0 2pt; border-radius: 2pt; color: #123; }
pre { background: #0f1720; color: #e7eef7; padding: 9pt 11pt; border-radius: 5pt;
      overflow: visible; white-space: pre-wrap; margin: 0 0 10pt; }
pre code { background: none; color: inherit; padding: 0; font-size: 8.6pt; line-height: 1.45; }

.chapter { page-break-before: always; }
.chapter h1 { border-bottom: 2.5pt solid #2b6cb0; padding-bottom: 6pt; margin-bottom: 12pt; }
.lede { font-size: 11.5pt; color: #3d4d5f; font-style: italic; margin-bottom: 14pt; }

.callout { border-left: 3.5pt solid #2b6cb0; background: #f2f6fb; padding: 8pt 11pt;
           margin: 0 0 11pt; border-radius: 0 4pt 4pt 0; }
.callout.warn { border-color: #c05621; background: #fdf5ee; }
.callout.tip { border-color: #2f855a; background: #f0f8f3; }
.callout b { color: #12304d; }

.practice { background: #eef7f1; border: 1pt solid #b7dcc4; border-radius: 5pt;
            padding: 10pt 13pt; margin-top: 14pt; page-break-inside: avoid; }
.practice h2 { margin-top: 0; color: #1c4532; }
.practice p { margin: 0; }

/* cover */
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center;
         page-break-after: always; text-align: left; }
.cover .eyebrow { letter-spacing: .22em; text-transform: uppercase; font-size: 9pt;
                  color: #2b6cb0; font-weight: 700; }
.cover h1 { font-size: 34pt; margin: 10pt 0 8pt; letter-spacing: -.02em; }
.cover .sub { font-size: 13pt; color: #44576c; max-width: 130mm; }
.cover .meta { margin-top: 26pt; font-size: 10pt; color: #5b6b7d; border-top: 1pt solid #d5dde6;
               padding-top: 10pt; }
.cover .rule { width: 40mm; height: 3pt; background: #2b6cb0; margin: 18pt 0; }

/* contents */
.toc { page-break-after: always; }
.toc h1 { font-size: 20pt; border-bottom: 2.5pt solid #2b6cb0; padding-bottom: 6pt; }
.toc ol { margin: 14pt 0 0 0; padding: 0; list-style: none; }
.toc li { padding: 6pt 0; border-bottom: .5pt dotted #cbd5e0; font-size: 11pt; }
.toc li .n { color: #2b6cb0; font-weight: 700; margin-right: 8pt; }
.toc li .s { color: #6b7c8f; font-size: 9.5pt; display: block; margin-top: 2pt; }
"""

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>{css}</style></head>
<body>
<section class="cover">
  <div class="eyebrow">LearnLoop · self-study</div>
  <h1>{title}</h1>
  <div class="rule"></div>
  <div class="sub">{subtitle}</div>
  <div class="meta">{meta}</div>
</section>
<section class="toc">
  <h1>Contents</h1>
  <ol>{toc}</ol>
</section>
{body}
</body></html>
"""

COURSES = {
    'core': {
        'title': 'Python Core',
        'subtitle': 'Nine chapters from the first line of code to files, exceptions and functions you can trust.',
        'fragments': ['core-ch01-03.html', 'core-ch04-06.html', 'core-ch07-09.html'],
        'meta': 'Chapters 1-9 · with auto-graded exercises on the LearnLoop site',
    },
    'applied': {
        'title': 'Python Applied',
        'subtitle': 'Turtle graphics, data with NumPy, Pandas and Matplotlib, and an honest first look at face detection and recognition.',
        'fragments': ['applied-ch10-12.html'],
        'meta': 'Chapters 10-12 · with auto-graded exercises on the LearnLoop site',
    },
}


def build(key: str) -> Path:
    spec = COURSES[key]
    parts = []
    for frag in spec['fragments']:
        p = ROOT / 'content' / frag
        if not p.exists():
            raise SystemExit(f'missing fragment: {p}')
        parts.append(p.read_text(encoding='utf-8'))

    body = '\n'.join(parts)
    chapters = re.findall(r'<h1>(Chapter\s+(\d+)\s*[—-]\s*([^<]+))</h1>', body)
    toc = ''.join(
        f'<li><span class="n">{n}</span>{title.strip()}<span class="s">{key}</span></li>'
        for full, n, title in chapters) or '<li>No chapters found</li>'

    html = HTML.format(title=spec['title'], subtitle=spec['subtitle'], meta=spec['meta'],
                       css=CSS, toc=toc, body=body)
    OUT.mkdir(exist_ok=True)
    html_path = OUT / f'{key}.html'
    pdf_path = OUT / f'{key}.pdf'
    html_path.write_text(html, encoding='utf-8')

    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
           '--no-pdf-header-footer', f'--print-to-pdf={pdf_path}',
           html_path.as_uri()]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if not pdf_path.exists():
        print(proc.stderr.decode('utf-8', 'replace')[-1200:])
        raise SystemExit('chrome did not produce a PDF')
    print(f'{key}: {pdf_path} ({pdf_path.stat().st_size/1024:.0f} KB), chapters={len(chapters)}')
    return pdf_path


if __name__ == '__main__':
    for k in (sys.argv[1:] or ['core', 'applied']):
        build(k)
