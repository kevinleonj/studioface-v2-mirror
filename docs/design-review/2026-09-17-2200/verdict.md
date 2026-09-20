# Verdict — real frontend, round 3 (final) — 2026-09-17 22:00

## Total: 39/50 — PASS (by the rubric's own rule), but short of your stated target

The rubric's actual pass/fail contract is: any line at 0 or 1 is an automatic blocker,
and total below 35 fails. Neither condition is triggered here (no 0s or 1s, total 39 ≥
35), so this **passes** the rubric as written.

But you asked for something stricter this round: **40/50 with no line below 3**. That
target is **not met** (39 total, and line 5 sits at 2) and, more importantly, **it is
not reachable right now regardless of what else improves** — see below.

## Is the 40/no-line-below-3 target reachable? Plainly: no, not yet.

Line 5 (value above the fold) is capped at 2 by the rubric's own explicit instruction
("a placeholder scores at most 2") until real before/after photographs exist — issue #6,
blocked on Kevin's own face and written consent. That is not a scoring choice I am
making; it is the floor the rubric itself sets for a placeholder. Every other line could
score a 5 and the "no line below 3" condition would still fail, because line 5 alone
violates it. So: **the no-line-below-3 target is structurally blocked on issue #6, full
stop, independent of the total.**

The 40-point total is a separate, softer question. At 39/50 with line 5 at its rubric
floor of 2, closing issue #3 (the legal entity name) would plausibly move line 6 from 4
to 5 and line 10 from 4 to 5 — call it +2, landing at 41/50 total. So **the 40-point
total is reachable today by closing issue #3 alone** (a one-line content fix, not code) —
but the *no-line-below-3* condition would still fail on line 5 until issue #6 closes too.
Both issues are named in your message as open and outside this task's scope; I am
reporting the arithmetic honestly rather than either inflating line 5 or pretending the
target is closer than it is.

## What actually worked, verified directly (not taken on trust)

1. **Font fix (`var(--font-fraunces)` → `var(--font-newsreader)`)** — **worked, on all
   three files.** `getComputedStyle` on the live H1 of `/recuperar/`, `/g/?o=...`, and
   `/legal/terminos/` all return the real `"Newsreader, \"Newsreader Fallback\""` font
   family (30px, 30px, 36px respectively), each visibly distinct from the 16px Public
   Sans body text on the same page. This was the single highest-leverage finding from
   round 2 and it is fully closed.
2. **`sf-focus` on the button base** — **worked.** Tabbing to the primary CTA after
   choosing a file returns `animationName:"sf-draw"`, `animationDuration:"0.22s"`, and a
   two-tone box-shadow ring in the site's own paper/accent colours — confirmed by
   `getComputedStyle`, not just by reading the CSS. The exact button the brief named is
   now the one that draws.
3. **Upload target hover/hidden-input/filename** — **worked.** Hover moves the label's
   `getComputedStyle` border from `#141312` to `#c3352b` and background from transparent
   to a light warm grey. The native input is `sr-only` (1px×1px, `clip-path:inset(50%)`)
   but still `tabIndex:0` and reachable by Tab — confirmed by a fresh-navigate keyboard
   trace landing on `#sf-files` first. After choosing a file, the label reads "1 de 4
   elegidas · Elegir otras fotos · landing-390x844.png" — the raw OS control is gone from
   view and the filename is reported back.
4. **`noValidate` + Spanish validation on `/recuperar/`** — **worked.** Submitting
   `notanemail` renders "Escribe un correo válido, por ejemplo nombre@dominio.com." in
   the site's own red, `role="alert"`, inline under the input — no native English bubble
   anywhere in the capture.

All four fixes verified, all four hold up.

## Lines below 3

- **Line 5 (value above the fold): 2/5** — blocked on issue #6 (real photographs +
  Kevin's consent). Not a code problem; nothing to fix in this codebase.

No other line is below 3. Lines 1, 4, 6, 7, 10 all carry open findings (see rubric.md)
but none drops under the 3 floor.

## Three highest-leverage changes (file:line), ordered by score-per-effort

1. `frontend/src/components/ui/button.tsx:29` — the `lg` button size is `h-9` (36px),
   8px under the 44px tap-target floor, and it is the one button the entire funnel and
   every euro of revenue runs through. Bumping `lg` to `h-11` (44px) is a one-token
   change that directly fixes line 7 and removes the only tap-target defect left.
2. `frontend/src/app/page.tsx:67` — the hero's `items-start` on an unequal-height
   two-column grid leaves a dead gap under the "Empieza aquí" card at 1440px
   (`getBoundingClientRect` confirmed: card ends 253px into the hero, left column runs
   ~300px further). Either stretch the card to the column height or move the trust copy
   into the gap; this is the one open item docking line 4 and partly line 1.
3. Legal Contacto block (`frontend/src/components/legal-page.tsx:33`,
   `[PENDIENTE: nombre o razón social]`) — a one-line content fix once Kevin supplies the
   registered name (issue #3). Closes most of the remaining gap on lines 6 and 10 for
   very little engineering effort; it is a content blocker, not a design one.

## One thing to keep

The verification discipline in the fix itself: `recuperar/page.tsx:24-27` leaves a
comment explaining *why* `noValidate` was chosen — not just what changed, but the exact
failure mode (an English bubble, in an uncontrolled typeface, on an all-Spanish product)
it prevents. That is the kind of comment that stops the next person from "helpfully"
re-adding `required` and undoing the fix. Worth keeping as the house style for every
future state-behavior fix.

## Captures

All requested states captured except the two that remain genuinely unreachable on a
static export with no backend: **preview-rendering** and **preview-rendered** (clicking
"Ver una prueba gratis" would call `/api/preview`, which does not exist on
`localhost:8903`; not invented, not worked around). Every other requested state —
landing (both sizes), upload hover, upload keyboard-focus (now correctly on the file
input, verified via a fresh-navigate Tab trace after an initial inconsistent reading was
discarded and rechecked), file-chosen, CTA keyboard-focus, gallery pending/error link
(both sizes — resolves to the same "enlace no válido o caducado" state as round 2, since
the backend that would validate `cs_test_probe123` is absent; this is the honest static-
export behavior, not a new regression), recuperar resting (both sizes) and
invalid-email-submitted, and `/legal/terminos/` (both sizes) — was captured and is on
disk beside this file. No capture silently failed. The static server on port 8903 was
killed at the end of this review; confirmed down (`curl` to `localhost:8903` returns no
response) before finishing, so `frontend/out` is free for the next build.
