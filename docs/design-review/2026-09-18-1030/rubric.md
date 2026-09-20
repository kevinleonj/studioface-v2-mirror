# StudioFace — round 5 design critique — rubric

Served from a COPY of `frontend/out` (`C:\Users\KEVIN\AppData\Local\Temp\sf-review-r5`), `python -m
http.server 8903`. Captures at 390x844 and 1440x900. Backend absent (static export only); `/g/`
states reached by placing literal JSON fixture files at
`sf-review-r5\api\orders\<order>\<token>` (e.g. `{"status":"delivered", ...}`) so the page's own
`fetch("/api/orders/<o>/<t>")` gets a real 200 response from the static server — not a code change,
not `frontend/out` itself. `/api/preview` on the landing page was stubbed the same way, by
overriding `window.fetch` in the page via `browser_evaluate`, to reach the rendering/rendered
states. Both methods are disclosed per-line below.

Colour contrast ratios below are computed by me (WCAG relative-luminance formula) from the hex
values in `frontend/src/app/globals.css`, not read off a tool — shown to two decimal places.

---

## 1. Decided or averaged — 4/5

The hero inset (`frontend/src/components/muestras.tsx:108-131`) is a specific, named shape with a
comment explaining *why* it beats the even pair, and `hero-proof.tsx:31-34` cites the exact pixel
measurement (`691px slot`, `85px of a 212px pair`) that justified the change. The colour system is
equally deliberate: I recomputed contrast for `--primary` (#c3352b) on `--background` (#f2f1ed) and
got **4.81:1**, and for `--destructive` (#a82a22) got **6.15:1** — both match the values claimed in
the CSS comments (globals.css:71, 95) to two decimal places, which only happens when someone actually
ran the numbers before shipping them. That is a designer's fingerprint.

It loses a point because the same discipline was not applied everywhere: `frontend/src/app/g/page.tsx:239`
and `:117-123` build their CTAs with bare `buttonVariants()` (no `size="lg"`), landing 32px buttons
back into three pages after the team wrote a named regression test
(`tests/test_tap_targets.py`) specifically to stop that from happening again (see line 7). A
system this considered should not have a hole exactly where its own test suite has a blind spot.

## 2. Typographic hierarchy and rhythm — 4/5

Computed at 390px (`getComputedStyle`, not read from source): H1 **38px** (the `clamp(38px,6.4vw,68px)`
floor engages at this width), price **28px**, FAQ question **20px**, body **16px**, labels/captions
**14px** (`text-sm`). That is a five-step scale (14/16/20/28/38, desktop H1 up to 68px) with
increasing ratios (1.25, 1.4, 1.36, 1.79) — not two sizes wearing different weights. Body line
length measured at 342px container width and 16px Public Sans wraps "Sube tus selfies y recibe
cuatro retratos para / LinkedIn, tu CV o tu web, hechos a partir de tu / cara y de nadie más." at
roughly 40-48 characters per line — inside the 45-75 guideline, if toward its short end on mobile.
H1 line-height 1.02 is tight by design for a display serif and reads fine at 38-68px.
Docked one point: the price block (28px, `page.tsx:71-73`) sits only 8px above the FAQ's own H2
scale-mate territory in visual weight to the *header's* price (14px, muted, `site-header.tsx:54`) —
two very different treatments of the identical string "19,99 €" on the same viewport, which is a
legitimate hierarchy question (see line 6).

## 3. Colour — 5/5

One dominant: paper `--background:#f2f1ed`. One accent, used sparingly (CTA fill, focus ring, price
NOT included — deliberately restrained): `--primary:#c3352b`. Depth without shadows: `--secondary:
#e6e4de` panels (the upload card) and 1px `--border:#141312` rules — a flat, contact-sheet material
vocabulary instead of elevation, which is a real, consistent choice, not an absence of one.
Contrast, computed by me from the hex values:
- foreground `#141312` on background `#f2f1ed`: **16.4:1** (comment claims 16.1:1 — within rounding).
- muted-foreground `#5c5851` on background (used for all secondary copy, including the header price
  and the "IVA incluido" line): **6.25:1** — clears 4.5:1 with margin.
- primary `#c3352b` on background: **4.81:1**, matches the code comment exactly.
- destructive `#a82a22` on background: **6.15:1**, matches the code comment exactly.
No text anywhere I measured fails 4.5:1.

## 4. Layout — 4/5

Desktop hero is a genuine asymmetric 7fr/5fr grid (`page.tsx:51`), not a centred stack. "Cómo
funciona" is 2fr/1fr/1fr (`page.tsx:96`, confirmed in `19-como-funciona-1440.png`: step 01 is
visibly wider than 02/03) — the cardocalypse tell is absent both in geometry and in the removal of
card chrome. FAQ is an intentional 2-column split (3 items left, 2 right on desktop), not three
equal boxes. Docked one point for a real, measured layout defect the design intends to prevent but
does not achieve: the "Más muestras" placeholder is `aspect-[2/1]` (`more-muestras.tsx:67`) while
the code comment directly above it claims "the same 4:5 frame the photographs will occupy, so
nothing jumps." I measured both states on the live page: placeholder height **171px** at 342px
width (2:1, as coded), loaded pair height **279.875px** — a **108.9px / 63.7%** growth the instant
the real content swaps in. That is exactly the "cardocalypse"-adjacent tell line 10 asks about, and
the audit script cannot see it because it never runs the IntersectionObserver.

## 5. Value above the fold — 5/5

The "después" photograph is real pipeline output (`muestras.tsx:1-12`, enforced by
`tests/test_demo_assets.py` against the built HTML, not just claimed in a comment), disclosed as AI
in both the visible caption and the alt text. At 390x844 with the consent banner up — the real
first-visit state — the hero photograph occupies y=292 to y=632, fully inside the 691px visible
slot (measured via `getBoundingClientRect`). A visitor sees an actual, specific, well-lit corporate
headshot directly under the H1 before they scroll. This is the product shown, not promised.

## 6. Trust for a Spanish buyer — 5/5

"19,99 €" appears with "IVA incluido, pago único" (`page.tsx:71-76`) and again, unlabelled, in the
header (`site-header.tsx:54`) — present on every viewport even though (per line 1/2) the full,
labelled price block itself is pushed below the first-visit fold (see verdict for the fold finding).
Photo retention is stated twice in different words: "las fotos que subes se borran a los 7 días" /
"los retratos quedan un año" (recuperar NOTES, `recuperar/page.tsx:33-36`) and again in the FAQ.
Refund condition is a single, named case ("si no conseguimos generar las cuatro fotos… No
devolvemos el importe porque el resultado no te guste", `faq.tsx:52-56`) — not a vague guarantee.
AI disclosure appears at least four times across the two pages I captured (hero caption, muestras
captions, gallery footer line, FAQ). Legal links (`Aviso legal`, `Privacidad`, `Términos`,
`Cookies`) and company identity (`limeralda, NIF Z3714124-C, Maria de Molina 31, Madrid`) are in the
footer on every page. A lost-gallery path exists in the header on every page ("Recuperar mis
fotos") and again in the footer.

## 7. Thumb reach and tap targets at 390px — 1/5 — BLOCKER

Landing's two CTAs are correctly 44px (`h-11`, `size="lg"`), and `tests/test_tap_targets.py` locks
that in for `upload-form.tsx` specifically. But I measured, with `getBoundingClientRect` on the live
page, every OTHER primary action on the two other pages in this round:
- `/g/` "Descargar" (the action that retrieves the product a customer just paid 19,99 € for),
  `g/page.tsx:117-123`: **32px** tall.
- `/g/` "Volver a intentarlo" (the refund/failure recovery CTA), `g/page.tsx:239`: **32px** tall.
- `/recuperar/` "Enviarme el enlace" (the only action on the page), `recuperar/page.tsx:` `<Button
  type="submit">` with no `size` prop, so it falls back to the `default` variant: **32px** tall.

All three come from `buttonVariants()` called with no `size` argument, or a bare `<a
className={buttonVariants()}>`, which defaults to `size: "default"` → `h-8` (`button.tsx:19-20`) —
**smaller than the 36px violation the team already found and fixed once** (`tests/test_tap_targets.py`
docstring, lines 1-16). `test_tap_targets.py`'s second test only regexes `<Button\b` tags inside
`upload-form.tsx`; it cannot see a bare `<a className={buttonVariants()}>` in a different file, so
this regression is invisible to the one test written expressly to catch this class of bug. This is
the exact moment a buyer collects the four photos they paid for, and it is below the floor on a
phone.

## 8. States — 5/5

Every state on the list was reached and is visibly, differently designed, not a browser default:
- **Hover** (`04-upload-hover-390.png`): dashed border flips from `--border` (black) to `--primary`
  (red) and lifts 3px (`sf-frame`, `globals.css:170-175`).
- **Chosen** (`05-file-chosen-390.png`): label text changes to "1 de 4 elegidas" / "Elegir otras
  fotos" / the real filename, and the CTA switches from a desaturated resting red to solid
  `--primary`.
- **Rendering** (`06-preview-rendering-390.png`, via a stubbed `/api/preview` fetch): "Preparando tu
  prueba. Tarda unos segundos." (`role="status"`) and the button label becomes "Generando tu
  prueba…", disabled.
- **Rendered** (`07-preview-rendered-390.png`): the free preview appears with `sf-arrive` (300ms
  rise), followed by the wardrobe select and the real checkout button.
- **Checkout focused via Tab** (`08-checkout-focus-390.png`): confirmed via real `Tab` keypress
  (not click) landing `document.activeElement` on the button. The ring is a visible two-tone
  box-shadow (`--background` inner ring + `--primary` outer ring, `globals.css:142-147`) that
  **appears instantly** — no transition property on `.sf-focus:focus-visible` — which is exactly
  what was asked for: a keyboard user should not wait to know where they are.
- **Invalid email** (`10-recuperar-invalid-email-390.png`): custom Spanish copy ("Escribe un correo
  válido, por ejemplo nombre@dominio.com."), red border on the input via `aria-invalid`, `role="alert"`
  — not the browser's native, unstyled, English validation bubble the code comment explicitly
  says it replaced (`recuperar/page.tsx:` `noValidate` comment).
- `/g/` processing (`12-gallery-working-390.png`, reached via a literal `{"status":"processing"}`
  fixture file served at the polled URL), delivered (`13-gallery-delivered-390.png`), refunded
  (`14-gallery-refunded-390.png`) and refund-pending (`15-gallery-refund-pending-390.png`) were all
  reached the same way and are all visually distinct, each with a CTA and the support address.

## 9. Motion — 5/5

Five named moments (`globals.css:167-203`), each with a stated trigger, property (opacity/transform
only) and duration (140/80/300/250/180ms, all under the team's self-imposed 400ms ceiling), all
inside `@media (prefers-reduced-motion: no-preference)`, with a global `reduce` fallback
(`globals.css:220-230`) that force-collapses any future animation to 1ms. The one thing round 4
explicitly fixed and I could verify directly: the focus ring's `box-shadow` has no `transition` —
it appears in a single frame, not drawn over 220ms as the old version did. Nothing loops, nothing
fires on page load, and I did not find a sixth undocumented moment.

## 10. Slop tells — 3/5

`python scripts/design_audit.py frontend/out` → **0 P0, 0 P1, 0 P2** — confirmed by running it
myself. Cross-checked against pixels and found the script clean on what it checks (no Inter/Fraunces
mix, no cream-on-cream, no stock-photo hero — the hero photograph is a specific, well-lit,
non-generic portrait, not a gradient blob or an icon). But two tells the script structurally cannot
see, both confirmed by measurement, not suspicion:
1. The "Más muestras" placeholder-to-real aspect-ratio mismatch (line 4): a **63.7% height jump**
   on load, contradicting the code's own "nothing jumps" comment. The script only reads static HTML;
   it never fires the `IntersectionObserver`.
2. The 32px tap targets on `/g/` and `/recuperar/` (line 7): a regression of a defect the team
   already named, fixed, and wrote a test for once — reappearing through a code path
   (`buttonVariants()` on a raw `<a>`, or `<Button>` with no `size` prop) that the existing
   regression test cannot see. A green test suite and a green audit both shipped this.
Neither is cosmetic — one is a page visibly jumping under a scrolling thumb, the other is the
exact control a paying customer needs. Score reflects that the *tooling* passed while the *product*
did not, twice, in ways a five-minute runtime check caught both times.

---

## Total: 41/50

Line 7 scores 1 → **blocker**, regardless of the total.
