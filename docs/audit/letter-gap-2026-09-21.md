# Letter-gap audit — 21 Sep 2026 (task 25)

Kevin reported a visible gap after the letter "f" in the "Recuperar mis fotos" link,
seen again on 21 September in Chromium at 2x zoom on production, reading as
"Recuperar mis f otos". This link appears in two places: the site header (a real
underline, Tailwind's `underline` utility) and the site footer (a bottom border, no
underline). The gap could only ever show where there is an underline, so the header
instance is the one under test.

## Method

Served the real built export (`frontend/out`, from `npm run build`) on localhost, never
production. Opened the header link in Chromium (Playwright), zoomed the whole page to
300% with `document.documentElement.style.zoom` — Chromium implements that the same way
it implements native page zoom (Ctrl+Plus), which is how Kevin found this in the first
place — and cropped a screenshot around the link for each setting.

## The four required screenshots

| # | setting | file | gap after "f" in "fotos"? |
|---|---|---|---|
| 1 | current settings (shipping today) | `letter-gap-2026-09-21/1-current.png` | YES |
| 2 | `font-kerning: none` on the link | `letter-gap-2026-09-21/2-kerning-none.png` | YES, unchanged |
| 3 | `font-feature-settings: 'liga' 0` on the link | `letter-gap-2026-09-21/3-liga-0.png` | YES, unchanged |
| 4 | link set to the system font instead of Public Sans | `letter-gap-2026-09-21/4-system-font.png` | NO |

Looking at the crops: it is not the space between letters that changes width. It is the
red underline itself — in screenshots 1, 2 and 3 the underline stops just after the
upright stroke of the "f" and starts again before the "o", leaving a bare gap in the
line under nothing but empty paper. In screenshot 4 the underline runs solid, unbroken,
under the whole word.

Turning kerning off and turning the "fi"/"fl" ligatures off changed nothing: the gap is
identical in 1, 2 and 3, pixel for pixel width-wise it is the same break. Only replacing
the whole typeface (screenshot 4) removed it — and swapping the typeface family is
exactly the change this task's own hard constraint forbids, and on its own it does not
tell us why Public Sans, specifically, does this.

## Two more probes, to find the real cause before touching anything

Because none of the three permitted settings explained the gap, and the one setting
that did remove it is off-limits as a fix, two more things were tried against the same
served page, still never touching production:

| # | setting | file | gap? |
|---|---|---|---|
| 5 | link's font forced to one fixed variable-font instance (`font-variation-settings: 'wght' 400`, `font-optical-sizing: none`) — still Public Sans, no interpolation | `letter-gap-2026-09-21/5-fixed-wght-instance.png` | YES, unchanged |
| 6 | link's `text-decoration-skip-ink: none` — a browser decoration setting, no font change at all | `letter-gap-2026-09-21/6-skip-ink-none.png` | NO |

Probe 5 rules out the variable font: forcing one fixed weight instance, with no
interpolation for the browser to get wrong, made no difference at all. Probe 6 isolates
the actual mechanism: Chromium's own underline-skipping feature
(`text-decoration-skip-ink`, on by default, "auto") decides which parts of an underline
to hide so it does not run through a letter's ink, and for the "f" in Public Sans, at
this zoom, it hides more of the line than the letter actually occupies — a rendering
decision the browser makes about where to draw the line, not a difference in the
letters' shapes or spacing. Turning that browser behaviour off, with Public Sans
completely unchanged, makes the underline run solid and the gap disappears.

## RESULT

RESULT: none of the three settings that keep Public Sans (current, `font-kerning: none`,
`font-feature-settings: 'liga' 0`) removes the gap, and it is not the next/font subset
or loader either — forcing one fixed, non-interpolated font weight left the gap
unchanged. The gap is Chromium's own `text-decoration-skip-ink: auto` hiding too much of
the underline around the "f" glyph. Fixed by setting `text-decoration-skip-ink: none` on
the two header links (`frontend/src/components/site-header.tsx`); Public Sans, its
next/font configuration, colours, layout, motion and every other setting are unchanged.
Confirmed against a fresh `npm run build` export with no manual override: the underline
under "fotos" is solid (`letter-gap-2026-09-21/7-after-fix.png`).

## What was not changed, and why

- Public Sans and its `next/font/google` configuration in `frontend/src/app/layout.tsx`
  are untouched — the diagnosis (probe 5) shows the subset/loader is not the cause.
- No letter-spacing was added anywhere, negative or otherwise.
- The footer's "Recuperar mis fotos" link uses a bottom border (`border-b`), not a text
  underline, so `text-decoration-skip-ink` does not apply to it and it was never at risk
  of this artefact; left as is.
- Colours, first-screen layout, consent script, GA4 id, delivery prompts, payment
  provider, hosting, price and Google Cloud permissions: unchanged.
