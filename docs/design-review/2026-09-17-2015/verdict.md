# Verdict — three directions — 2026-09-17 20:15

## Scores

| Variant | Total | Verdict |
|---|---|---|
| A — Cuarto oscuro | 34/50 | **FAIL** — line 4 (Layout) = 1, a blocker on its own |
| B — Hoja de contactos | 40/50 | PASS |
| C — Carné | 37/50 | PASS |

## Ship: B — Hoja de contactos

B wins on the line that matters most: it is the only direction where every choice — the
all-monospace body, the persistent numbered rail, the underline-not-colour emphasis device
— is mechanically different from the other two, not a re-hex of the same trick (see rubric
line 1). It also has no layout blocker; A's does (see below), and C's asymmetric facts grid
(2fr/1fr/1fr) is the one thing it does better than B's `repeat(3,1fr)`, but that alone isn't
enough to close an 8-point gap.

**What choosing B costs:** the all-monospace running body copy (b.html:20-21) is the
riskiest bet of the three for this specific buyer — a Spanish professional on a phone
deciding whether to trust a stranger with their face reads monospace as "technical
document," not "photography studio," until real content proves otherwise. That is a
legibility-of-intent risk B takes on deliberately that C's humanist Public Sans body does
not. Ship B accepting that trade, and verify it with real users before it's load-bearing on
conversion copy.

## Blockers

- **A, line 4 (Layout) = 1.** At 1440x900 the H1, price, and CTA are entirely below the
  fold (a-1440x900.png). Root cause: `.frame`'s negative-margin bleed (a.html:49) plus
  `align-items:end` on `.hero` (a.html:29) — the frame becomes very tall at wide viewports
  and pulls the text column's bottom-aligned content off-screen with it. This directly
  violates DESIGN.md's own requirement that price sit above the fold and the H1 be the LCP
  element. A is not shippable as-is regardless of its total.

## Three highest-leverage changes for B (file:line)

1. `docs/design-variants/b.html:63` — `.facts{...grid-template-columns:repeat(3,1fr)...}`.
   Replace with an asymmetric split (e.g. `2fr 1fr 1fr`, as c.html:54 already does) to
   remove the three-equal-column geometry DESIGN.md explicitly bans, even though it has no
   card chrome here.
2. `docs/design-variants/b.html:20-21` — `font-family:"Chivo Mono"` on `body` sets the
   running lede, facts copy, and footer text in monospace. Keep Chivo Mono for labels and
   frame numbers only (its actual job), and set a humanist serif or sans for the lede,
   `.facts p`, and footer body text, so the page reads as a considered studio object rather
   than a technical readout to a non-technical buyer.
3. `docs/design-variants/b.html:54-58` — the two-frame placeholder block sits directly
   under the CTA on the phone capture (b-390x844.png) and competes with it for the first
   thing the eye lands on. Give the placeholder frames a clearly secondary treatment (lower
   contrast, or below the trust facts) so price → CTA reads first, placeholder second.

## One thing to keep from each loser

- **From A:** the safelight-orange focus-ring `draw` animation paired with the frame's
  `MUESTRA` corner tag (a.html:44-46, 53-54) — a specific, on-brand piece of art direction,
  worth carrying over once the desktop overflow bug is fixed.
- **From C:** the asymmetric `2fr 1fr 1fr` facts grid (c.html:54) and the
  `prefers-reduced-motion` guard on the headline animation (c.html:69) — both are small,
  portable code decisions B should simply copy.

## Captures

All nine screenshots captured successfully: `a-390x844.png`, `a-390x844-focus.png`,
`a-1440x900.png`, `b-390x844.png`, `b-390x844-focus.png`, `b-1440x900.png`, `c-390x844.png`,
`c-390x844-focus.png`, `c-1440x900.png`. No capture failed. The six interaction states in
the design-critic brief (hover, file-chosen, rendering, rendered, keyboard-focus, invalid
email) mostly do not exist on these static mocks — only keyboard-focus (captured for all
three) and hover (visible in code, not separately screenshotted) apply; upload-chosen,
rendering, rendered, and the recuperar error state require the real backend and were not
scored here, per the brief's instruction not to invent states that don't exist.
