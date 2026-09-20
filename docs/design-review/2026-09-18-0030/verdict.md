# Verdict — round 4, real before/after photographs — 2026-09-18 00:30

## Total: 38/50 — PASS (≥35), no line below 3, short of the stated 40 target by 2

No line scores 0 or 1, so there is no automatic blocker. The lowest lines are three 3s
(colour, layout, thumb reach) — all real, all named below — not a structural floor like round
3's line-5 cap. The "no line below 3" condition is **met** for the first time in this loop. The
40-point target is not met; the gap is small and the three changes below would plausibly close
it (roughly +1 each on lines 3, 4, 7 if all three land: 41/50).

## Lines below 4 (none below 3)

- **Line 3 (colour) — 3/5**: the error/alert red resolves to `rgb(231,0,11)`, measured at
  **4.22:1** against the `#F2F1ED` background — under the 4.5:1 floor for body text — on the
  exact text meant to tell a user their input or their free preview failed. It is also a second,
  off-brand red distinct from the site's `#C3352B` accent.
- **Line 4 (layout) — 3/5**: `/recuperar/` and the `/g/` invalid-link state both leave roughly
  400px of empty background between the last interactive element and the footer, at both
  390×844 and 1440×900. The landing page's asymmetry is real; the two secondary states didn't
  get the same attention.
- **Line 7 (thumb reach / tap targets) — 3/5**: the cookie-consent banner's "Rechazar" and
  "Aceptar" buttons measure 32px tall (`getBoundingClientRect`, live) — the shadcn `default`
  size, never bumped to `lg` like every other button on the site — 12px under the 44px floor,
  on the two controls nearly every visitor taps first.

## The hero-pair question, answered directly

**It communicates, it does not merely decorate — but it is undersized for the job.** The pair is
a real, disclosed photograph (not an icon, not a mockup), it sits fully inside the first
viewport at both 390×844 (`figure` bottom at y=756 of 844) and 1440×900, and the transformation
is legible at a glance: unkempt hair and dim bathroom light next to combed hair, an office
backdrop and a collared shirt. That is a genuine "show, don't tell" above the fold, which is what
line 5 was blocked on. But at 390px each panel is only 169.5×211.875 CSS pixels, splitting the
width evenly between the "antes" (which nobody is buying) and the "después" (which is the entire
purchase decision) — and the two pairs in "Más muestras," identically sized, read as visibly more
convincing simply because there's more visual context around them lower on the page competing
for less attention. **A large "after" with a small "before" inset would likely convert better**:
it would give the one image that matters roughly double the linear size for the same footprint,
and a small corner-inset "antes" still discharges the "real transformation, not a fabricated
result" disclosure obligation without spending half the hero's width on the thing being replaced.
This is a genuine trade-off, not a free win — the current 2-up is more legible as "before/after
evidence" to a skeptical first-time visitor, and an inset before/after is a slightly less
immediately-legible convention. I would test it, not assume it, but if forced to bet, the inset
wins on a phone screen where every pixel of the "después" face is doing sales work.

## The cookie banner and the withdrawal-rights text: confirmed, and it is a real problem

At `/legal/terminos/`, 390×844, **on first paint, with no scroll**: the "Derecho de
desistimiento" paragraph's absolute position is y=572–740 in the document; the fixed cookie
banner occupies the bottom 117px of the viewport (y=727–844 in viewport terms) at scroll
position zero. The overlap is small in absolute terms — about 13px — but it lands exactly on the
**last line of the paragraph**, which is the statute citation itself: a pixel crop
(`terminos-390-crop.png`) shows "Legislativo 1/2007" sliced through the vertical centre of the
glyphs by the banner's top rule, the citation for the specific article (103.m, Real Decreto
Legislativo 1/2007) that establishes the digital-content exception to the right of withdrawal —
the one sentence on this page whose exact wording is what's supposed to make the "no refunds
because you don't like the result" answer in the FAQ legally sound. At 1440×900 the same
mechanism clips a *different* paragraph ("Uso aceptable," the minors/consent clause) at first
paint, confirming this is a structural property of a fixed-position banner over a
legally-dense page, not a one-off coincidence at one breakpoint. **This is a real defect, not
cosmetic**: it is legally load-bearing text, obscured before any user interaction, on the one
page in the site whose entire purpose is legal disclosure. It resolves itself the instant the
user scrolls or dismisses the banner, which is the only thing keeping it from being worse — but
"resolves after the user notices something is cut off" is not the same as "was never cut off."

## Three highest-leverage changes, file:line, ordered by score-per-effort

1. `frontend/src/components/consent.tsx:109` and `:118` — the two `<Button>` calls inside
   `ConsentBanner` render at the shadcn default size (32px). Add `size="lg"` to both. One prop on
   two call sites, fixes line 7's only remaining real defect, and it is the single most-tapped
   control on the entire site.
2. `frontend/src/components/consent.tsx:99` — the banner is `fixed inset-x-0 bottom-0` with no
   awareness of the content underneath it. Cheapest fix: add `scroll-padding-bottom` (or a
   bottom-margin/spacer) sized to the banner's own height on `/legal/*` routes specifically, or
   render the banner `sticky` inside a bottom-padded wrapper instead of `fixed` over the whole
   viewport, so it never sits on top of statutory text at scroll position zero. Directly closes
   the line 6/8 legal-text-obscured finding.
3. `frontend/src/app/globals.css:66` -- `--destructive: oklch(0.577 0.245 27.325);` is the
   unmodified shadcn default, never repointed to the brand palette the way `--primary` (line 58
   in the same block, resolving to `#C3352B` live), `--background` and `--border` all were.
   Repoint it to a red in the `#C3352B` family, darkened enough to clear 4.5:1 against `#F2F1ED`
   (`#A02B22` or similar tests out close) -- fixes line 3's only real defect and removes the
   second, undecided red flagged in line 10 in one edit.

A fourth item, cheaper than all three but smaller in effect, worth naming: the empty ~400px
gap on `/recuperar/` and `/g/` (line 4) is a one-file layout fix (vertical-centre the message
block, or reduce the section's forced min-height) but moves the score less than the three above
because it is not a legal or contrast defect, only an unfinished-looking one.

## One thing to keep

The keyboard-focus trace on the CTA (`cta-focus-390x844.png`): `getComputedStyle` after a real
Tab press (not a click) returns a two-tone box-shadow in the site's own paper and accent colours,
`animationName: "sf-draw"`, and a button height of exactly 44px — three separate round-3 and
round-4 findings (default focus ring, undersized CTA, and "does the fix actually hold on the
live DOM") all verified true at once, on the one control the entire funnel runs through. Keep
building the habit of proving state fixes against `getComputedStyle` on a real interaction trace
rather than trusting the source diff — it is what caught that the *cookie banner* buttons never
got the same treatment.

## Captures

All requested states captured except the two that remain structurally unreachable on a static
export with no backend, exactly as in round 3: **preview-rendering** (the fetch to a dead host
rejects in under 100ms, too fast to sustain a loading frame — code inspected instead,
`upload-form.tsx:75-92`) and **preview-rendered / checkout-focus** (both require a `handle` from
a real `/api/preview` response; the `<select>` and second `<Button>` are gated behind
`{handle ? … }` in `upload-form.tsx:213-238`, confirmed by reading the source, not invented).
Every other requested state — landing resting and muestras-scrolled (both sizes), upload hover,
file-chosen, preview-error (backend absent, honest failure captured), CTA keyboard-focus (via a
genuine Tab trace), recuperar resting and invalid-email-submitted (both sizes), gallery
pending/invalid-link (both sizes), and `/legal/terminos/` resting plus the desistimiento crop
(both sizes) — was captured and sits beside this file. The static server on port 8905 was
served from a **copy** at a scratch directory (`frontend/out` was never served in place), and
was killed at the end of this review; `curl --max-time 2 http://localhost:8905/` returned
connection-refused (status `000`) before finishing, confirming `frontend/out` is free for the
next build.
