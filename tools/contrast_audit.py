"""WCAG contrast audit for the LearnLoop palette.

Run: python tools/contrast_audit.py
Prints each pair with its ratio and whether it clears 4.5:1 (body text) or 3:1 (large/UI).
"""
from __future__ import annotations


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(hex_color: str) -> float:
    h = hex_color.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg: str, bg: str) -> float:
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg: str, alpha: float, bg: str) -> str:
    f = [int(fg.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(bg.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    out = [round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3)]
    return '#%02x%02x%02x' % tuple(out)


BG = '#0a0d12'
PANEL = '#131a24'
PANEL2 = '#182230'
INPUT = '#0c1118'
CODE = '#0a1017'

PAIRS = [
    ('body text', '#e8eef6', BG, 4.5),
    ('muted on bg', '#8fa1b5', BG, 4.5),
    ('muted on panel', '#8fa1b5', PANEL, 4.5),
    ('dim on bg (meta)', '#64748b', BG, 4.5),
    ('dim on panel (meta)', '#64748b', PANEL, 4.5),
    ('hero paragraph', '#c3d0de', PANEL, 4.5),
    ('reader paragraph', '#dbe6f2', PANEL, 4.5),
    ('accent link on bg', '#3fd0e0', BG, 4.5),
    ('accent on panel', '#3fd0e0', PANEL, 4.5),
    ('amber on panel', '#f6ad55', PANEL, 4.5),
    ('green on panel', '#45d483', PANEL, 4.5),
    ('red on panel', '#f2617a', PANEL, 4.5),
    ('tag text on tag bg', '#8fa1b5', '#1a2432', 4.5),
    ('code comment on code bg', '#6f8194', CODE, 4.5),
    ('admin badge', '#b7a6ff', blend('#7c5cff', 0.16, PANEL), 4.5),
    ('primary button label', '#06121a', '#3fd0e0', 4.5),
    ('nav link on bar', '#8fa1b5', blend('#0a0d12', 0.82, BG), 4.5),
    ('input text on input bg', '#e8eef6', INPUT, 4.5),
    ('placeholder-ish dim on panel-2', '#64748b', PANEL2, 4.5),
    ('focus ring vs panel', '#3fd0e0', PANEL, 3.0),
]

CANDIDATES = {
    'dim → #7e91a8': '#7e91a8',
    'dim → #8698ae': '#8698ae',
    'dim → #8b9db1': '#8b9db1',
    'muted → #9aacc0': '#9aacc0',
    'comment → #8595a8': '#8595a8',
    'comment → #8fa0b3': '#8fa0b3',
}


def main() -> None:
    print(f'{"pair":34} {"fg":9} {"bg":9} {"ratio":>6}  need  verdict')
    worst = []
    for name, fg, bg, need in PAIRS:
        r = ratio(fg, bg)
        ok = 'PASS' if r >= need else 'FAIL'
        print(f'{name:34} {fg:9} {bg:9} {r:6.2f}  {need:3.1f}   {ok}')
        if r < need:
            worst.append(name)
    print('\nFailing pairs:', ', '.join(worst) if worst else 'none')

    print('\nCandidate replacements (checked against bg, panel, panel-2, tag bg):')
    for label, color in CANDIDATES.items():
        rows = [f'{where}={ratio(color, bgc):.2f}'
                for where, bgc in (('bg', BG), ('panel', PANEL), ('panel2', PANEL2), ('tag', '#1a2432'))]
        print(f'  {label:22} {color}  ' + '  '.join(rows))


if __name__ == '__main__':
    main()
