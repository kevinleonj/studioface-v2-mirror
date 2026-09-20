# Design critique — three directions — 2026-09-17 20:15

Captured with `python -m http.server 8901` over `docs/design-variants/`, Playwright at
390x844 and 1440x900. Screenshots beside this file: `a-390x844.png`, `a-390x844-focus.png`,
`a-1440x900.png`, `b-390x844.png`, `b-390x844-focus.png`, `b-1440x900.png`, `c-390x844.png`,
`c-390x844-focus.png`, `c-1440x900.png`. `scripts/design_audit.py docs/design-variants` ran
clean: `0 P0, 0 P1, 0 P2`.

These are static mocks: no backend, no real photos. Line 5 is capped at 2 for all three
(honest placeholder, not a fake). Line 8 is scored only on the focus-visible and hover CSS
that exists; loading/empty/error are not implementable here and are not scored.

---

## A — Cuarto oscuro

| # | Line | Score | Evidence |
|---|---|---|---|
| 1 | Decided or averaged | 4 | The 7/5 grid with the headline overlapping a bleeding photo frame (a.html:29,49) and the safelight-orange `MUESTRA` corner tag (a.html:53-54) are real spatial decisions, not a repaint of a template — but the wordmark device (`Studio` + accent-coloured `Face`, a.html:25-26) is the *identical* mechanism used in b.html:33-35 and c.html:24-25, just re-hexed, so not every choice here was actually re-decided. |
| 2 | Typographic hierarchy | 4 | H1 `clamp(40px,7.2vw,78px)` at line-height .96 (a.html:32) reads as a genuine display size against the 19px lede and 21px price (a-390x844.png); the lede's `max-width:34ch` (a.html:34) renders lines of roughly 30 characters in the phone capture — under the 45–75ch band. |
| 3 | Colour | 5 | `#12100E` dominant / `#F0531C` accent / `#F5F2EE` text, plus a distinct `#1C1917` surface for the frame — visible in a-390x844.png as a lighter charcoal rectangle against the near-black page, i.e. real depth, not a flat two-tone. |
| 4 | Layout | 1 | **Blocker.** At 1440x900 (a-1440x900.png) only a sliver of "Tu foto de perf…" is visible at the very bottom pixel row; the price and CTA are entirely below the fold. Cause: `.frame`'s negative `margin-right` bleed (a.html:49) widens the 5fr column far past the 1180px wrap at 1440px viewport width, and `aspect-ratio:4/5` turns that width into a very tall box; `align-items:end` on `.hero` (a.html:29) then bottom-aligns the text column to that tall row, pushing the H1/price/CTA down off-screen. DESIGN.md itself requires "price above the fold" and "LCP element is the H1" — both fail here. Additionally `.trust` reverts to `repeat(3,1fr)` (a.html:56), the exact three-equal-column geometry DESIGN.md bans, even without card chrome. |
| 5 | Value above the fold | 2 | Honest placeholder only — "Aquí aparecerá un ejemplo real…" (a.html:89) — capped per rubric; at 1440 it is also the *only* content visible in the fold because of the line-4 bug. |
| 6 | Trust for a Spanish buyer | 5 | IVA incluido inline with price (a.html:85), refund condition ("Si no salen cuatro, no cobramos", a.html:97-98), deletion timing (7 days / 1 year, a.html:94-96), no-account/link recovery (a.html:99-100), footer legal links + `/recuperar/` + AI disclosure (a.html:105-106) — all present. |
| 7 | Thumb reach / tap targets | 3 | CTA `min-height:52px` (a.html:40) clears 44px; footer legal links are bare underlined text with no padding (a.html:105) — a likely sub-44px tap target on the exact page that must send someone to `/recuperar/`. |
| 8 | States | 3 | Focus-visible is a two-ring box-shadow with a `draw` keyframe (a.html:44-46), confirmed distinct from a default ring in a-390x844-focus.png; hover is a 1px `translateY` (a.html:42). No loading/empty/error reachable in a static mock. |
| 9 | Motion | 4 | Two named moments only: photo crossfade on arrival (unverifiable, no real image yet) and the focus-ring draw (confirmed on screen). Nothing decorative beyond that in the CSS. |
| 10 | Slop tells | 3 | `design_audit.py` found nothing (0/0/0). Visually: the `repeat(3,1fr)` trust row (a.html:56) is the cardocalypse geometry the script can't see because it has no card chrome; the shared wordmark mechanism (see line 1) is a mild template-reuse tell. |

**Total A: 34/50 — FAIL** (below 35, and line 4 is a 0/1 blocker on its own).

---

## B — Hoja de contactos

| # | Line | Score | Evidence |
|---|---|---|---|
| 1 | Decided or averaged | 5 | Running body copy set entirely in Chivo Mono (b.html:20) and a persistent vertical rail carrying "HOJA 01 / STUDIOFACE" (b.html:80) are a committed, unusual information architecture; the emphasis device — a 3px accent underline under "foto de perfil profesional" (b.html:39) — is mechanically different from A's and C's colour-fill trick, i.e. an actually distinct decision, not a re-hex. |
| 2 | Typographic hierarchy | 5 | Newsreader serif H1 `clamp(38px,6.4vw,68px)` (b.html:37) against 15px Chivo Mono body and 11px letter-spaced facts labels (b.html:64) is a real three-step scale; the monospace measure keeps the lede within a stable ~45-char line at 1440 (b-1440x900.png). |
| 3 | Colour | 5 | `#F2F1ED` paper / `#141312` ink (16.1:1) / `#C3352B` accent (5.9:1) — one dominant, one sharp accent, no third competing hue, confirmed in both captures (warm off-white page, red used only for underline, CTA, rail dot, and frame numbers). |
| 4 | Layout | 4 | The 4rem/1fr rail persists at both breakpoints (b-390x844.png keeps the vertical rail column at 2.25rem, b.html:72) with no overflow bug. Docked one point: `.facts` at desktop is `repeat(3,1fr)` (b.html:63) — the same three-equal-column tell as A. |
| 5 | Value above the fold | 2 | Two honest placeholder frames, one of which turns the absence into copy ("Sin ejemplos inventados", b.html:95) — still a placeholder, capped per rubric. |
| 6 | Trust for a Spanish buyer | 5 | Same completeness as A: IVA incluido (b.html:90), refund (b.html:101), deletion timing (b.html:100), no-account/recovery (b.html:102), footer legal + recuperar + AI disclosure (b.html:106-107). |
| 7 | Thumb reach / tap targets | 3 | CTA `min-height:52px` (b.html:49) is fine; footer links share the same unpadded bare-text risk as A (b.html:106). |
| 8 | States | 4 | Focus-visible is a heavy `outline:3px solid var(--ink)` offset 3px (b.html:51) — confirmed in b-390x844-focus.png as a thick black double-line frame around the red button, the most deliberately "ink-stamped" of the three treatments, clearly not a default ring. |
| 9 | Motion | 3 | Only one of the two DESIGN.md-promised moments is actually in the CSS: the frame hover-lift (b.html:54-58). A "determinate progress rule during generation" is asserted in DESIGN.md but not present anywhere in b.html — an under-delivery against the spec, not a fabrication, but worth flagging plainly. |
| 10 | Slop tells | 4 | Audit script clean. All-monospace body is a genuine audience-fit question (does a Spanish non-technical buyer read mono-space body copy as "considered" or as "developer tool"?) rather than a crude tell; the `repeat(3,1fr)` facts row (b.html:63) is the same geometry tell noted at line 4. |

**Total B: 40/50 — PASS**, no line at 0 or 1.

---

## C — Carné

| # | Line | Score | Evidence |
|---|---|---|---|
| 1 | Decided or averaged | 3 | Archivo Black at up to 92px (c.html:30) and a hard-left, deliberately unbalanced 1.35fr/.85fr grid (c.html:29) are real choices, but the overall grammar — white background, black text, one bold sans headline, teal 4px-rounded CTA (c.html:41-42), 6px-rounded dashed drop-zone (c.html:46) — is the closest of the three to a confident, generic startup template; unlike A's darkroom or B's contact sheet, C has no physical-studio referent of its own. |
| 2 | Typographic hierarchy | 3 | At 1440x900 the headline wraps into five short lines, one of them just "Tu" alone (c-1440x900.png) — a large scale step (17px body vs up-to-92px display) but a ragged, uneven line composition that undercuts the hierarchy it's built for. |
| 3 | Colour | 4 | `#FFFFFF` / `#0B0B0B` (19.6:1) / `#00706B` (5.1:1) confirmed clean in both captures; restrained and correctly cited, but combined with the rounded button/drop-zone shapes it reads as the most "generic modern product" palette-and-shape pairing of the three. |
| 4 | Layout | 5 | The only variant whose full hero — headline, price, CTA, and drop-zone — fits inside 1440x900 with no overflow (c-1440x900.png); `.facts` at desktop is `2fr 1fr 1fr` (c.html:54), not equal thirds, so it avoids the cardocalypse tell that both A and B have. |
| 5 | Value above the fold | 2 | Honest dashed-border "MUESTRA" placeholder (c.html:87), no faked result — capped per rubric. |
| 6 | Trust for a Spanish buyer | 5 | Same completeness: IVA incluido (c.html:82), refund (c.html:96), deletion timing (c.html:93-94), no-account/recovery (c.html:98), footer legal + recuperar + AI disclosure (c.html:103-104). |
| 7 | Thumb reach / tap targets | 4 | CTA `min-height:52px` (c.html:42); the more compact hero (line 4) means price and CTA sit higher on the phone capture than in A or B, reaching them needs less scroll (c-390x844.png). Footer links share the same bare-text risk as the other two. |
| 8 | States | 4 | Focus-visible is `outline:3px solid var(--ink)` offset 3px (c.html:43), confirmed in c-390x844-focus.png as a clean thick black outline, clearly deliberate; the drop-zone has a defined hover/drag-over border-and-background change (c.html:49) though not itself screenshotted mid-hover. |
| 9 | Motion | 4 | Two named moments — a one-time 240ms headline settle (c.html:33-34) and the drop-zone hover/drag response (c.html:49) — and it is the only one of the three to guard motion with `prefers-reduced-motion` (c.html:69). |
| 10 | Slop tells | 3 | Audit script clean, and no crude single tell (no violet, no gradient, no equal-thirds cards) — but the overall gestalt (rounded CTA + rounded dashed drop-zone + teal accent + humanist sans body) is the one of the three most easily mistaken for a well-typeset SaaS landing page, which is exactly the failure mode DESIGN.md names. |

**Total C: 37/50 — PASS**, no line at 0 or 1.

---

## Comparison

| Variant | Total | Verdict | Blockers |
|---|---|---|---|
| A — Cuarto oscuro | 34/50 | FAIL | Line 4 = 1 (hero content off-screen at 1440x900) |
| B — Hoja de contactos | 40/50 | PASS | none |
| C — Carné | 37/50 | PASS | none |
