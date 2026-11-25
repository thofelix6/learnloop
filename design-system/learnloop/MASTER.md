# LearnLoop — design system (MASTER)

Adopted 2026-11-26. Replaces the original cyan/violet "glass card" look.

## Direction

**Data-dense study console, editorial reading surface.** The plan and admin screens borrow the
structure of an analytics dashboard (KPI row, dense rows, 8–12 px padding); the session view turns
into a quiet reading page with a 66-character measure. One accent carries action and progress; the
rest is ink and slate so code and long text stay legible.

## Where it came from (UI UX Pro Max)

| Query | Result used |
|---|---|
| `--domain style "dark data dense dashboard"` | **Data-Dense Dashboard** — KPI cards, dense rows, 12-column grids, minimal padding, sticky headers, dark-mode supported |
| `--domain color "developer tool dark technical"` | **Developer Tool / IDE** palette — background `#0F172A`, card `#1B2336`, muted foreground `#94A3B8`, "run green" accent, dark label on accent |
| `--domain typography "technical editorial geometric sans"` | Geometric-sans display + neutral grotesque body (Outfit + Public Sans implemented) |
| `--domain ux "dashboard information hierarchy"` | One primary action per screen, scannable labels, progressive disclosure |

Rejected with reason: the `--design-system` generator matched *Claymorphism* + Baloo 2 / Comic Neue
because "learning" routes to children's education. That is wrong for a code-heavy 30-session LLM
course, so only the rule-based datasets above were applied — the skill's own guidance is to verify fit
and not to persist unverified output.

## Tokens

```
--bg        #0b1120   page, darkest surface
--surface   #131c2e   panels, rail
--surface-2 #1b2336   raised rows, inputs, code header
--line      #2a3549   1 px borders (never a shadow-only edge)
--text      #f8fafc   18.0:1 on bg
--text-2    #a8b6c9   8.3:1 on surface
--text-3    #8697ad   5.7:1 on surface — the lightest value allowed for text
--accent    #4ade80   9.8:1 on surface; "run green"
--accent-ink#06210f   9.8:1 on accent (labels on primary buttons)
--blue      #93b4f0   8.1:1 — links, focus ring, secondary data
--amber     #fbbf24   10.2:1 — waiting / due
--danger    #ef4444   4.5:1 — destructive only, never body text
```

Type: **Outfit** (display/numerals, self-hosted variable, 32 KB) + **Public Sans** (UI + reading,
27 KB) + system mono stack for code (`Cascadia Mono`, `Consolas`).
Scale: display 34/1.05, h1 26/1.15, h2 18/1.3, h3 12/1.4 caps +0.12em, body 15/1.6, small 13/1.5,
micro 12/1.4, reading 16.5/1.75. Radii 10 (controls) / 14 (panels) / 999 (chips). Spacing 4·8·12·16·24·32.
Grid gutters 14 px, panel padding 18–20 px, dense row height 56 px, tables 36 px.

## Layout

- ≥1080 px: fixed 268 px rail (brand, course switcher, nav, progress, legal links) + content column
  (max 1120 px) + optional 320 px session rail.
- 760–1079 px: rail collapses to top bar + horizontal nav.
- <760 px: top bar with menu, bottom tab bar (Plan · Exercises · Search · More), drawer for
  admin/settings/course switch/legal. Touch targets ≥44 px.

## Components

`btn` (primary / ghost / danger / sm), `chip` (+ ok / warn / info), `panel`, `kpi`, `bar`, `ring`,
`srow` (dense session row), `paper` (reading surface), `codebox` (editor chrome), `table`, `cookie`,
`toast`, `doc`.

## Rules

- One primary action per screen (lime). Everything else is ghost or text.
- Never rely on colour alone: done/waiting/blocked always carry a word or glyph.
- Focus visible on every interactive element (2 px blue, offset 2).
- `prefers-reduced-motion` removes transitions; no motion that carries meaning.
- Contrast ≥4.5:1 for text, ≥3:1 for UI — enforced by `tools/contrast_audit.py` and the browser audit.
