# Rubric — round 4, real before/after photographs — 2026-09-18 00:30

Served from a copy at `<scratchpad>/sf-r4` on `localhost:8905` (never `frontend/out` directly,
per this round's hard rule). Copy made with `cp -r frontend/out .../sf-r4`; server killed and
`curl` to port 8905 confirmed connection-refused before finishing.

## 1. Decided or averaged — 4/5

The contact-sheet direction is applied with intent and holds across all five routes: hard 1px
rules (`border-[color:var(--border)]`, `#141312`), no shadow anywhere in any capture, Chivo Mono
frame labels (`sf-label`, 11px, 0.2em tracking, uppercase) against Newsreader display type, a
red underline (`border-b-[3px]`, `#C3352B`) carried under the bolded H1 phrase on the landing
page. This is a specific, recognisable choice, not a default. Docked one point for one
unreconciled leftover: the error/`destructive` colour token resolves to `rgb(231,0,11)`
(`getComputedStyle` on `[role="alert"]`), a different, more saturated red than the brand accent
`#C3352B` used everywhere else — a second, undecided red sitting inside a system whose whole
premise is "one dominant, one accent."

## 2. Typographic hierarchy and rhythm — 4/5

H1 `clamp(38px,6.4vw,68px)` at `leading-[1.02]`, measured 38px/`font-size` on the live 390px
DOM; body copy under it capped at `max-w-[52ch]` (52 characters, inside the 45–75 target);
price set at 28px Newsreader; `sf-label` eyebrows at 11px Chivo Mono. `/legal/terminos/` H2s are
`text-xl` (20px) over `text-[color:var(--muted-foreground)]` body at the Tailwind default 16px,
body column capped `max-w-prose` (~65ch, confirmed by the wrapped line lengths in the 1440
capture, e.g. "Por 19,99 €, IVA incluido, recibes cuatro imágenes de perfil generadas con
inteligencia" at roughly 68 characters). Steps are clear (38/28/20/16/11) though not tied to a
single named ratio the way DESIGN.md's spacing scale is.

## 3. Colour — 3/5

Palette as specified: background `#F2F1ED`, foreground `#141312` (16.1:1, confirmed in round 3
and unchanged), accent `#C3352B`, `--muted-foreground` `#5C5851` on `#F2F1ED` computes to
**6.13:1** (own calculation from the resolved RGB triples, sRGB relative-luminance formula) —
comfortably clears 4.5:1 for body text. But the error-state red fails: `rgb(231,0,11)` on
`#F2F1ED` computes to **4.22:1** — under the 4.5:1 floor for normal text — verified two ways
(canvas `fillStyle` resolution of the `lab()` value, then the WCAG formula in-page) and visible
on both `/recuperar/`'s "Escribe un correo válido…" message and the landing page's "No hemos
podido generar la prueba." alert. Separately, the "Antes"/"Después" labels on the muestra photos
are the accent colour with **no scrim or background chip**, laid directly on uncontrolled photo
content — a crop of the "Después" label on the hombre-30 photo (`despues-label-crop.png`) shows
it sitting on a mid-grey wall, legible but low-contrast, and the ratio would vary photo to photo
since nothing constrains it. One accent, but two reds and one uncontrolled-contrast placement.

## 4. Layout — 3/5

Landing hero is a genuine 7fr/5fr asymmetric split (`grid-cols-[7fr_5fr]`), "Cómo funciona" is
2fr/1fr/1fr (not equal thirds — the cardocalypse tell named in DESIGN.md is explicitly avoided),
no card chrome, no shadows. But `/recuperar/` and `/g/?o=...` (pending/invalid-link state) both
leave a large dead zone: on `/recuperar/` at 390×844 there is roughly 400px of empty background
between the error message/button and the footer rule (`recuperar-error-390x844.png`); the same
gap appears at 1440×900, from y≈230 to y≈785 (`recuperar-error-1440x900.png`). The gallery's
invalid-link state repeats the same pattern (`gallery-390x844.png`, `gallery-1440x900.png`).
These are two of the six captured page-states with unresolved empty canvas — a page that had
decided its landing layout did not carry that decision to its secondary states.

## 5. Value above the fold — 4/5

No longer a placeholder. The hero pairs a real `<picture>` (`mujer-40-antes.jpg` /
`-despues.jpg`) inside a ruled 2-up frame, `loading="eager"`, confirmed rendered and **within**
the first viewport at 390×844: `getBoundingClientRect()` puts the figure at y=504–756, i.e.
fully visible before any scroll (viewport height 844). At 1440×900 it sits beside the H1 with no
scrolling at all (`landing-1440x900-fold.png`). The transformation itself reads clearly — messy
hair/dim bathroom light next to combed hair/office backdrop/collared shirt — and both facts
(fictitious "antes" model, real pipeline "después") are disclosed in a visible caption under
every pair, not just alt text. Not a 5: each panel is only 169.5×211.875 CSS px at 390 wide, so
the "después" face — the actual purchase decision — gets only half that width to prove itself,
and the two extra pairs in "Más muestras" (`landing-390x844-muestras.png`) are demonstrably more
convincing at the same size, which suggests the hero panel is undersized relative to what the
asset can do, not that the asset is weak.

## 6. Trust for a Spanish buyer — 4/5

Price "19,99 €" with "IVA incluido" above the fold; refund condition stated exactly once and
precisely ("En un caso: si no conseguimos generar las cuatro fotos…"); AI disclosure repeated in
three places (hero subhead, price block, every muestra caption); deletion policy in the FAQ ("Las
que subes se borran a los 7 días. Los retratos quedan un año."); `/legal/aviso-legal/` names a
real trader — "Titular: limeralda. NIF: Z3714124-C. Domicilio: Maria de Molina 31, Madrid" — no
`[PENDIENTE]` anywhere (confirmed by reading the live page source, not just the component
comment); footer links to all four legal pages plus "Recuperar mis fotos" on every page. Docked
one point because the withdrawal-rights citation on `/legal/terminos/` — the specific statute
number a consumer needs to see to know the AI-generated-content exception is lawfully disclosed
— is visually clipped by the fixed cookie banner at first paint (see line 8 and the verdict for
the measurement); the text exists in the DOM and reads fine after dismissing the banner or
scrolling, but "present in the DOM" is not the same as "delivered," and this is the one page
where that distinction is a legal one, not a cosmetic one.

## 7. Thumb reach and tap targets at 390px — 3/5

The round-3 finding is fixed and verified: the primary CTA (`Button size="lg"`) measures
**44px** tall live (`getBoundingClientRect().height` on the focused button = 44), matching the
`h-11` token now in `button.tsx`. But a new, more universal defect exists: the cookie-consent
banner's "Rechazar" and "Aceptar" buttons — the two controls almost every visitor on almost every
page will tap before doing anything else — measure **32px** tall
(`getBoundingClientRect()` on both, confirmed live), 12px under the 44px floor, because
`ConsentBanner` renders `<Button>` at the shadcn `default` size instead of `lg`. This is not an
edge case; it is the single most-tapped control on the site by volume.

## 8. States — 4/5

Hover: verified — the upload label's border goes from `#141312` (border) to the computed accent
on `:hover`, background shifts to the secondary warm-grey, and it visibly lifts (`translateY:
-3px`, `.sf-frame:hover`, confirmed against `globals.css:240-242`). File-chosen: verified — label
switches to "1 de 4 elegidas · Elegir otras fotos · mujer-40-antes.jpg". Keyboard focus on the
CTA: verified via a genuine Tab trace (not a click) landing on the button, `getComputedStyle`
returns a two-tone `box-shadow` (`0 0 0 2px #F2F1ED, 0 0 0 5px #C3352B`) plus `animationName:
"sf-draw"`, `animationDuration: "0.22s"` — a designed ring, not a browser default. Error state on
`/recuperar/`: the site's own red inline message, `role="alert"`, no native bubble. Preview
error (backend absent, as expected on a static export): clicking "Ver una prueba gratis" throws
a fetch failure that resolves to "No hemos podido generar la prueba." in the same styled alert —
reachable and honestly captured rather than faked. Not reachable at all: preview-**rendering**
(the fetch to `/api/preview` rejects in well under 100ms against a dead host, so there is no
sustained loading frame to capture) and preview-**rendered** / checkout-button-focus (both
require a `handle` from a real `/api/preview` response, which does not exist in a static
export — confirmed by reading `upload-form.tsx:75-108`, the `<select>` and the second `<Button>`
are conditionally rendered only inside `{handle ? … }`). Docked for two real defects that land
squarely on "states": the error alert's red fails contrast (line 3) and the cookie-banner dialog
state clips legally-relevant text on the one page where that matters (line 6).

## 9. Motion — 5/5

Exactly two named moments, both purposeful, both traced to source: (1) `.sf-frame:hover {
transform: translateY(-3px) }` — the interactive frame you can actually act on (the upload
target) lifts on hover, not a decorative photo frame; (2) `.sf-focus:focus-visible` runs the
`sf-draw` keyframe (0.22s), tied to keyboard navigation reaching an interactive control, and both
are wrapped in a single `prefers-reduced-motion: reduce` block that zeroes them out
(`globals.css:228-234`). No entrance animations, no scroll-triggered reveals, no autoplay found
in `globals.css` or the four page files greped for `animate|transition|@keyframes`.

## 10. Slop tells — 4/5

`python scripts/design_audit.py frontend/out` → **0 P0, 0 P1, 0 P2, PASS**. Cross-checked
visually against every capture: no violet/indigo, no gradient text, no untouched shadcn card, no
emoji, no cream+serif+sage trio, no centred-hero-plus-three-cards (the landing hero is
asymmetric 7/5 and "Cómo funciona" is 2/1/1). Two tells the script cannot see, both found by
looking: the cookie banner's buttons are the *default* shadcn size (`h-8`) never reconsidered for
a product where every other button on the page was deliberately bumped to `h-11` — a component
pulled in and left at its factory setting, which is the exact "nobody decided" signature this
whole review exists to catch; and the second, off-brand destructive red (line 3) is the same
kind of default-token leftover. Both are small, but they are real instances of the thing the
rubric is built to find, sitting inside a page that otherwise clears the floor cleanly.

## Total: 38/50
