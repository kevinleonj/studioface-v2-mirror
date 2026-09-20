# Verdict — real frontend, round 2 — 2026-09-17 21:15

## Total: 32/50 — FAIL

Below the 35 floor, well short of the 40 target the brief asked for. No line scored
0 or 1, so there is no single automatic blocker under that rule, but the total fails
on its own, and lines 5, 8 and 10 all sit at the rubric floor of 2/5.

## The three fixes, plainly

1. **"Cómo funciona" 2fr/1fr/1fr** — **worked.** `frontend/src/app/page.tsx:107`
   ships the asymmetric grid; landing-1440x900.png shows column one at roughly 555px
   against ~275px for the other two. It no longer scans as three equal columns.
2. **Body copy moved to Public Sans, mono kept for labels** — **worked on the
   homepage, but the fix never reached the rest of the site.** Home shows a real
   three-step scale (Newsreader H1 / Public Sans body / Chivo Mono labels,
   page.tsx:70,77,86). But `/recuperar/`, `/g/`, and all four `/legal/*` pages still
   call `font-[family-name:var(--font-fraunces)]` for their H1s
   (`frontend/src/app/recuperar/page.tsx:45`, `frontend/src/app/g/page.tsx:79`,
   `frontend/src/components/legal-page.tsx:21`) — Fraunces is the exact serif
   DESIGN.md killed, the CSS variable is defined nowhere in the build, and those
   headings silently fall back to plain Public Sans at weight 400, indistinguishable
   from body text. So: yes on distinctiveness where it shipped, but it only shipped
   on one route out of seven.
3. **Sample frames moved below trust content** — **worked.** Confirmed in both
   landing-390x844.png and upload-filechosen-390x844.png: "Muestras" sits after the
   FAQ, well below the CTA, and does not compete for the same thumb.

## Carryovers, checked directly

- Focus ring **draws** (0.22s): true only for the footer legal `<a>` links
  (`.sf-focus:focus-visible{animation:.22s ease-out sf-draw}`). It is **not** wired to
  `components/ui/button.tsx`, so the primary CTA — the exact element the brief asked
  me to Tab to — gets the generic shadcn ring instead (`animation:none`, confirmed via
  `getComputedStyle`). Partial credit, wrong element.
- **No shadow anywhere**: true. `getComputedStyle` on the hero card and the CTA both
  return `boxShadow: none`.
- **Radius 0**: true. `--radius:0px`, confirmed computed on both card and button.
- **Wordmark no longer split-coloured**: true. Footer reads plain "Studioface", no
  "Studio"+accent-"Face" device anywhere in the build.

## Blockers

None at the single-line 0/1 level. But the total fails, and I would not ship this:
the site presents as decided for exactly one URL and averaged (or actively broken)
for the other six a real buyer will hit — recovering a lost gallery, reading the
terms they're about to accept, or waiting on their order.

## Three highest-leverage changes (file:line)

1. `frontend/src/app/recuperar/page.tsx:45`, `frontend/src/app/g/page.tsx:79`,
   `frontend/src/components/legal-page.tsx:21` — replace
   `var(--font-fraunces)` with `var(--font-newsreader)` (or the equivalent Tailwind
   class already used on `page.tsx:70`). One token, three files, and every secondary
   route regains the hierarchy and identity the homepage already has. Highest
   leverage in the whole review: it single-handedly fixes lines 1, 2 and most of 10.
2. `frontend/src/components/ui/button.tsx:6` — add `sf-focus` to the base button
   class list (or move the `.sf-draw` keyframe onto `focus-visible:ring` there
   directly) so the CTA the buyer actually pays through gets the bespoke ring, not the
   shadcn default. Small diff, fixes the worst part of line 8.
3. Legal contact block (built from whatever data source feeds `legal-page.tsx`'s
   Contacto section, rendering `[PENDIENTE: nombre o razón social]` verbatim in
   `legal-terminos-390x844.png`) — fill in the real company name before this is
   public. It is a one-line content fix that is currently undermining line 6 on the
   single page whose entire job is to earn trust.

Runner-up, cheaper than all three: style the native `<input type="file">` in
`frontend/src/components/upload-form.tsx:124-134` (or visually hide it and drive
selection off the label's own click, `display:none` + `aria-hidden` alternative) so
the funnel's first tap target isn't a 20px-tall OS control inside a hand-typeset page.

## One thing to keep

The `prefers-reduced-motion` guard wrapping *both* motion moments in one rule
(`@media(prefers-reduced-motion:reduce){.sf-focus:focus-visible,.sf-frame{transition:
none;animation:none}}`) — it is exactly the kind of small, correct, unglamorous
decision that's easy to skip and wasn't skipped here.

## Captures

All requested states captured except: preview-rendering and preview-rendered
(genuinely unreachable — no backend on localhost, `fetch` to `/api/preview` fails
immediately, confirmed via console error on the gallery route). Every other requested
state — landing (both sizes), upload hover, upload keyboard-focus (lands on the native
file input, not the button — reported as found), file-chosen, CTA keyboard-focus
(after a file is chosen and the button enables), gallery pending/error (both sizes),
recuperar resting (both sizes) and invalid-email submitted, and one legal page — was
captured and is on disk beside this file. No capture silently failed.
