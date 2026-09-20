# StudioFace — round 6 re-verification — verdict

**PASS.** 49/50, no blocker, no line under 4.

Server: `frontend/out` (rebuilt, commit `87455fa`) was copied to
`C:\Users\KEVIN\AppData\Local\Temp\sf-review-r6` before serving (`python -m http.server 8904` run
from inside the copy). The copy, not `frontend/out` itself, was served throughout. **The server was
killed before finishing this review** (`taskkill /PID 35740 /F`, confirmed with a follow-up `curl`
returning connection-refused / `000`).

## 1. The blocker — cleared, verified independently

I measured every `a`, `button`, `input`, `select` and `summary` on `/`, `/recuperar/`, and all five
`/g/` states (working, delivered, refunded, refund-pending, notfound) with `getBoundingClientRect`
on the live DOM — not by reading the class names. Every one is 44px except the two you named:

- `<input type="file">` on `/`: **1×1**, `sr-only`, reached via its `<label for="sf-files">` which
  is well over 44px. **Agreed exempt** — the label is the real target for every input modality.
- `hola@studioface.app`: **135.78–135.88 × 16px** on `/g/`'s three terminal states and
  `/recuperar/`. Inline in a sentence, WCAG 2.2 SC 2.5.8 exception 3 (Level AA) applies verbatim.
  **Agreed exempt** — padding an inline mailto link to a 44px box would break the sentence for no
  reachability gain.

I did not find a fourth thing under 44px that you missed. `tests/test_tap_targets.py` passed 7/7
when I ran it (`.venv\Scripts\python.exe -m pytest tests/test_tap_targets.py -q`), and the new
`test_the_patterns_can_actually_fail` is itself worth noting: it verifies the regex patterns used to
catch this class of bug are not silently inert, which is exactly how the 32px controls got past a
green suite the first time. Line 7: **5/5**, blocker cleared.

## 2. The placeholder jump — verified independently, confirmed 0.0%

Measured at 390×844, 342px container width: placeholder height **279.75px**, loaded-figure height
**279.875px** — a 0.125px / 0.045% difference, which is the 0.0% you claimed within measurement
noise. I did not use my suggested `aspect-[1.222/1]`; your fix (making the placeholder BE a
`<figure>` containing an `aspect-[8/5]` box plus the real caption string rendered `invisible`,
`more-muestras.tsx:63-74`) is the better one — it derives the height from the same content the real
figure will hold, so it cannot drift back out of sync the way a hand-picked ratio could if the
caption copy or the pair's aspect ratio ever changes again. I was not able to catch the placeholder
mid-transition in a screenshot (same issue as round 5: the 400px `rootMargin` fires faster than the
tool's navigate→scroll→screenshot round trip on a local server), so the visual evidence is the
paired measurement, not a photograph of the jump not happening. Line 4: **5/5**.

## 3. The header price — reads as a price, not clutter

At 390px the header wraps to three rows: wordmark, then the two nav links side by side, then "19,99
€ IVA incl." alone on its own line, 14px, `--muted-foreground` (#5c5851) — measured at y=112–132,
fully inside the real 691px first-visit slot (banner still at y=691, unchanged this round). It reads
as a subordinate, muted line under the primary nav, not as a fourth item competing for the same
visual weight — the wrap itself demotes it, and the colour and size already separated it from the
two links before this change. At 1440px it sits on the same row as the links with room to spare
(`02-landing-1440x900.png`) and reads even more clearly as a price tag, not a nav item.

One thing I'd flag, not fail: "IVA incl." is an abbreviation where the body copy two screens down
still says "IVA incluido" in full. That is a minor register mismatch — abbreviated in the header,
spelled out in the body — for a piece of information Spanish consumer law cares about being
unambiguous. I would not block on it; if you want a single wording, "IVA incl." is fine as
long as nothing else on the page shortens it differently, which today it does not.

## 4. Slop tells — every round-5 tell named, and which remain

Round 5 counted exactly two runtime tells (the audit script cannot see either):
1. The `aspect-[2/1]` placeholder against an ~8:5 real pair, measured as a 63.7% height jump.
2. 32px tap targets on `/g/` and `/recuperar/`, reachable through `buttonVariants()` on a bare `<a>`
   and a `<Button>` with no `size` prop — invisible to the then-existing test's `<Button\b` regex
   scoped to one file.

Both are closed, both re-measured by me independently above (line 4 → 0.045%, line 7 → 44px
everywhere but the two named exceptions). `python scripts/design_audit.py frontend/out` is still
0 P0/P1/P2, re-run by me. I looked for a new tell introduced by this round's changes (a taller input
throwing off the `/recuperar/` form's rhythm, a taller button breaking `/g/`'s grid) and found none
— `03-recuperar-390.png` and `04-gallery-delivered-390.png` both show clean, evenly spaced layouts
at the new sizes. Line 10: **5/5**.

## Re-scored lines, plainly

- **Line 1 (decided or averaged): 4/5 → 5/5.** The one hole in an otherwise decided system is
  closed, and closed with a self-audit (`test_the_patterns_can_actually_fail`) rather than just a
  patch.
- **Line 2 (typography): 4/5 → 4/5, unchanged.** Not touched by this round's diff. The dock is
  narrower than it sounds: the price string now has three visual treatments on one mobile viewport
  (28px serif + 14px muted header + the same 14px muted repeated in the FAQ answer), which is a
  hierarchy-consistency note, not a defect — and it is arguably the correct trade given line 6/3
  above. I'm not softening it to close the round, since nothing changed here to justify a different
  number.
- **Line 4 (layout): 4/5 → 5/5.** Placeholder-jump defect closed and independently verified at
  0.045%.

## Full re-score

Total 41/50 → **49/50**. No line below 4. No blocker.

## Captures that failed or required a workaround

- Same workaround as round 5, disclosed the same way: `/g/`'s four states were reached via literal
  JSON fixture files served at `sf-review-r6\api\orders\<order>\<token>` on the served COPY, not
  through a real backend, not through any code or `frontend/out` change.
- I could not photograph the placeholder mid-transition (see line 2 above); the independent
  measurement stands in for it.
- Everything else (landing at both sizes, `/recuperar/` resting and keyboard-focus, `/g/` delivered
  at both sizes, header at both sizes) was captured directly against the served static export, no
  stubbing.

## Screenshots (in this folder)

`01-landing-firstvisit-390.png` (consent banner up, real first visit, header price visible in the
691px slot) · `02-landing-1440x900.png` · `03-recuperar-390.png` ·
`04-gallery-delivered-390.png` (44px "Descargar" buttons visible) ·
`05-recuperar-submit-focus-390.png` (keyboard focus ring on the now-44px submit button) ·
`06-mas-muestras-placeholder-390.png` (already-loaded by capture time, per the timing note in line
2 above — the measurement, not this screenshot, is the evidence for the 0.0% shift).
