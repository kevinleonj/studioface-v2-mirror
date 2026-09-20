# StudioFace — round 6 re-verification — rubric

Served from a fresh COPY of the rebuilt `frontend/out` (`C:\Users\KEVIN\AppData\Local\Temp\sf-review-r6`,
`python -m http.server 8904`), against commit `87455fa`. `design_audit.py frontend/out` →
**0 P0, 0 P1, 0 P2**, re-run by me. `.venv\Scripts\python.exe -m pytest tests/test_tap_targets.py -q`
→ **7 passed**, re-run by me. `/g/` states reached the same way as round 5: literal JSON fixture
files served at `sf-review-r6\api\orders\<order>\<token>`, not a code change, not `frontend/out`
itself. Every measurement below is `getBoundingClientRect`/`getComputedStyle` on the live DOM, not
read off CSS source.

Only lines 1, 2, 4, 7 and 10 are re-scored with new evidence, per the coordinator's ask. Lines 3, 5,
6, 8, 9 were not targeted by this round's changes; I spot-checked what the diff touched (focus ring
on the now-taller `/recuperar/` submit button, confirmed still instant and correctly styled,
`05-recuperar-submit-focus-390.png`) and carry the round-5 scores forward for the rest, unchanged.

---

## 1. Decided or averaged — 5/5 (was 4/5)

Round 5 docked this line because the tap-target discipline visible in `button.tsx`'s own comment
(44px, tested) did not reach three other CTAs and a text input — a decided system with a hole in
its own execution. That hole is closed and I could not reopen it: I measured every `a`, `button`,
`input`, `select` and `summary` on `/`, `/recuperar/`, and all five `/g/` states (working, delivered,
refunded, refund-pending, notfound) with `getBoundingClientRect`. Every one is **44px** tall except
two, both of which I agree are correctly exempt (see line 7). The fix commit also did what a decided
team does with a near-miss: it wrote `test_the_patterns_can_actually_fail`
(`tests/test_tap_targets.py:139-146`) after finding that a `\b` word-boundary in a regex had reached
the file as a literal backspace byte and silently matched nothing, twice, in two different files —
a self-audit of the audit, not just a fix. Combined with the colour math from round 5 (primary
4.81:1, destructive 6.15:1, both matching the code comments to two decimals) and the hero inset
math, this now reads as a system that closes its own gaps rather than one that has them found for it.

## 2. Typographic hierarchy and rhythm — 4/5 (unchanged)

Not touched by this round's diff (`git diff` shows no changes to `page.tsx`'s H1/price block or
`globals.css`'s scale), and my re-measurement confirms the same computed sizes as round 5: H1
**38px** at 390px width, price **28px**, FAQ question **20px**, body **16px**, small/label text
**14px**. The dock stands for the same reason: the identical string "19,99 €" now carries THREE
different typographic treatments visible on the same mobile viewport — 28px serif with "IVA
incluido, pago único" on its own two lines in the body (still below the fold, y=845 at 390×844),
14px muted sans "19,99 € IVA incl." in the header (inside the fold, confirmed at y=112–132), and
nothing in between bridging them. That is a legitimate hierarchy question, not a typography defect
in isolation — the header treatment is new since round 5 and is the right call for line 6 (trust),
but it does not resolve this line, which is about a single element's weight consistency, not about
whether the information exists. UNSCORED-adjacent honesty: I did not check line-height or weight
values beyond what the computed `font-size` calls report, so this is about scale-step count and the
repeated-string observation only.

## 3. Colour — 5/5 (carried forward, not re-verified this round)

Not touched by the diff. Round-5 contrast computations (foreground 16.4:1, muted-foreground 6.25:1,
primary 4.81:1, destructive 6.15:1, all against `--background:#f2f1ed`) stand; I did not recompute
them this round since no CSS custom property changed.

## 4. Layout — 5/5 (was 4/5)

Independently re-measured the exact defect that docked this line. Placeholder height at 390×844,
342px container width, before the `IntersectionObserver` fires: **279.75px**. Height of the same
figure after scrolling to trigger the real load: **279.875px**. That is a **0.125px / 0.045%**
difference — effectively the 0.0% the coordinator claimed, and nothing I would call a shift. The
fix (`more-muestras.tsx:63-74`) makes the placeholder BE a `<figure>` with an `aspect-[8/5]` box
(matching two 4:5 images side by side, which is 8:5, not the old `2:1`) plus the real caption
string rendered `invisible` underneath it, so the two heights are computed from the same content
rather than a guessed ratio — the kind of fix that cannot drift back out of sync the way a
hand-picked number can. No cardocalypse, no other layout defect found on re-inspection.

## 5. Value above the fold — 5/5 (carried forward)

Unchanged: hero photograph still occupies the visible slot on first load (not re-measured this
round; the hero component was not in the diff).

## 6. Trust for a Spanish buyer — 5/5 (carried forward; see line 3 of the verdict for the header-price read)

Unchanged content requirements (retention, refund condition, AI disclosure, legal links, recovery
path) still present, not re-verified line-by-line this round since none of that copy changed. The
header price change is assessed under the coordinator's specific question in verdict.md rather than
re-scored here, since it is a presentation change to information that was already being credited on
this line.

## 7. Thumb reach and tap targets at 390px — 5/5 (was 1/5 — BLOCKER CLEARED)

Full re-measurement, every page and state, `getBoundingClientRect`:

| Control | Page/state | h |
|---|---|---|
| "Descargar" ×4 | `/g/` delivered | **44px** (was 32px) |
| "Volver a intentarlo" | `/g/` refunded, refund-pending | **44px** (was 32px) |
| "Recuperar mi enlace" | `/g/` notfound | **44px** |
| "Enviarme el enlace" | `/recuperar/` | **44px** (was 32px) |
| email `<input>` | `/recuperar/` | **44px** (was 32px) |
| "Ver una prueba gratis" / "Comprar las cuatro fotos por 19,99 €" | `/` | **44px** |
| wardrobe `<select>` | `/` | **47px** |
| header wordmark, "Cómo funciona", "Recuperar mis fotos" | every page | **44px** |
| footer legal links, "Política de cookies", "Rechazar"/"Aceptar" | every page | **44px** |
| all FAQ `<summary>` | `/` | **44px** |

Two elements are under 44px and I agree both are correctly exempt, for the reasons given:
- The `<input type="file">` on `/` measures **1×1** — it is visually hidden (`sr-only`) and
  functionally reached through its `<label for="sf-files">`, which I measured at well over 44px
  (a `py-8` block, ~172px tall in round 5's capture). A sighted or keyboard user never targets the
  1×1 element directly; a screen-reader user activates it via the label, which is the actual target.
  Correctly exempt.
- `hola@studioface.app` measures **135.78–135.88 × 16px** on `/g/`'s three terminal states and
  `/recuperar/`. It is an inline `<a>` inside a sentence ("¿Necesitas ayuda? Escríbenos a
  hola@studioface.app con el correo del pedido…"), and WCAG 2.2 SC 2.5.8 (Level AA) exception 3 is
  exactly "the target is in a sentence." Padding it to a 44px box would break the sentence it sits
  in for no accessibility gain — target-size guidance exists to stop mis-taps between adjacent
  controls, and a run of prose is not that. Correctly exempt. I agree with both.

I found nothing else under the floor. `tests/test_tap_targets.py` passed 7/7 when I ran it, including
`test_the_patterns_can_actually_fail`, which is itself worth crediting: a test suite that also
verifies its own patterns are not silently inert closes exactly the failure mode that let the
32px controls ship unnoticed twice.

## 8. States — 5/5 (carried forward; focus ring spot-checked)

`button.tsx` was not in this round's diff. I re-Tabbed to the now-44px `/recuperar/` submit button
(`05-recuperar-submit-focus-390.png`) to confirm the focus ring survived being attached to a taller
element: it did, same two-tone instant box-shadow, no transition. All five `/g/` states (working,
delivered, refunded, refund-pending, notfound) still render distinctly and correctly.

## 9. Motion — 5/5 (carried forward, not re-verified this round)

`globals.css` motion rules untouched by the diff.

## 10. Slop tells — 5/5 (was 3/5)

Every tell I named in round 5 is now closed, and I found no new one:
1. **The placeholder/loaded aspect-ratio mismatch** (line 4 of round 5) — closed. Re-measured at
   0.045% difference, effectively 0.0%, by construction (the placeholder IS the figure now) rather
   than by a better-guessed ratio, which is why I don't expect it to drift back.
2. **The 32px tap targets reachable through `buttonVariants()` on a bare `<a>` and an unset
   `<Button>` size prop** (line 7 of round 5) — closed. Re-measured at 44px on every instance I
   could find, and the fix shipped with a new regression test category
   (`test_no_link_styled_as_a_button_takes_the_default_size`,
   `test_the_one_text_field_in_the_product_is_thumb_sized`) plus a meta-test proving those patterns
   can actually fail — the exact class of tooling gap that let both tells through a green suite the
   first time.
`python scripts/design_audit.py frontend/out` is still 0 P0/P1/P2, re-run by me. I checked the diff's
one unrelated change (the Turnstile `afterInteractive`-timing fix in `upload-form.tsx`) for any new
visual regression and found none reachable in this static export — `TURNSTILE_SITEKEY` is empty
here, so that code path never renders in my captures; it is a functional fix outside this rubric's
scope, not a design tell.

---

## Total: 49/50

No line scores below 4. No blocker. **This now passes.**
