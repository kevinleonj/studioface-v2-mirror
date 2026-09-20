# Design decision — 18 Sep 2026 (supersedes the 17 Sep decision below)

## The rules I was breaking

Measured, not felt. `scripts/design_audit.py` against a fresh build, after I fixed the
detector's own blind spot:

    P0  allcaps-tracked-eyebrow (skill cluster 5)   51 uses of sf-label
    P0  broadsheet-default (cluster 3)              1px rules + --radius:0 + mono labels
    P1  headline-single-phrase-accent               the red rule under the bolded H1 phrase
    P1  tinted-near-black (cluster 5)               --foreground:#0a0a0a, five times

Three of this page's signature devices are named defaults in Anthropic's own
calibration list, and the fourth is an untouched shadcn token I never repointed. The
skill's sharpest line applies to all four: *a component left at its factory setting is
the signature this whole review exists to catch.*

I could not read `/mnt/skills/public/frontend-design/SKILL.md` — it is not on this
machine. I am working from the clusters quoted in the brief and reproduced in
`.claude/skills/studioface-ui/SKILL.md`, and saying so rather than implying otherwise.

## Pass 1 — the plan

**Colour.** Five hexes, one dominant, one accent, no second red.

| token | hex | role | measured on its background |
|---|---|---|---|
| `--background` | `#F2F1ED` | paper | — |
| `--foreground` | `#141312` | ink | 16.1:1 |
| `--muted-foreground` | `#5C5851` | secondary prose | 7.3:1 |
| `--primary` | `#C3352B` | the one accent | 4.81:1 |
| `--destructive` | `#A82A22` | errors only | 6.15:1 |

**Type.** Newsreader for headlines, Public Sans for everything else. **Chivo Mono is
deleted.** It existed only to set `.sf-label`, which is the cluster-5 device; removing
the family removes the temptation and one font download.

**Layout concept — "the print on the table".** The structure comes from the
photographs, not from rules between columns.

    390x844                          1440x900
    +------------------------+       +--------------------------------------+
    | header  wordmark  ...  |       | header  wordmark   cómo  precio  rec |
    +------------------------+       +--------------------------------------+
    |                        |       |                    |                 |
    |   BEFORE / AFTER       |       |  H1 (2 lines)      |  BEFORE/AFTER   |
    |   full bleed, drag     |       |  lede              |  large, drag    |
    |   [====||====]         |       |  precio            |  [====||====]   |
    |                        |       |  CTA               |                 |
    +------------------------+       +--------------------------------------+
    |  H1                    |       the image column is 5/12 and bleeds
    |  lede, precio          |       right; the text column is left-aligned
    +------------------------+       to a single axis, never centred
    |  upload panel          |
    +------------------------+

Alignment: one left axis for all text at both sizes. The image is the only element
allowed to break it.

**Principles.** Structure by image and whitespace. One heavy rule where a section truly
ends, never a hairline grid. Radius 10px on interactive chrome, 0 on photographs —
a print has square corners, a button does not.

## Pass 2 — reviewing that plan before writing code

Three things in pass 1 were what I would produce for any brief, so they changed:

1. **"Hairlines everywhere" was still in my head.** Pass 1 said "one heavy rule where a
   section ends". Even that is the broadsheet reflex. Changed to: sections are separated
   by space alone, and the only rule on the page is the one under the header.
2. **I had kept an eyebrow, renamed.** Pass 1's wireframe had a small label above the
   H1. That is the same device with the tracking removed. Deleted outright — the H1 is
   the first thing.
3. **Radius 10px on everything** is the shadcn default posture. Changed to: radius only
   where a finger lands (button, input, select). Panels get none, because they are not
   objects, they are regions.

## The direction decision: differentiate, not replace

**Keep B, and kill the three devices that make it cluster 3.** The reason is that the
cluster is carried by the *devices*, not by the palette or the typeface: paper, ink,
film-leader red and a Newsreader/Public Sans pairing are not a broadsheet. Hairline
rules, zero radius and tracked mono labels are. Replacing the direction would throw away
four decisions that survive their own audit in order to avoid three that do not.

The boldness is spent in exactly one place, as the skill requires: **the before/after is
full-bleed at the top of the first viewport and the divider is dragged by the visitor.**
That device comes from photography — it is how a retoucher shows work — and not from
newsprint. Everything else on the page is quiet.

## The hero shape: measured, not argued (18 Sep 2026)

Two shapes were built and served from copies of the real export, then measured at
390x844 and 1440x900 **with the consent banner up**, because the banner is up on every
first visit. That single correction changes the question: the usable slot on a phone is
**691px, not 844** (banner 153px), and on a desktop 823px (banner 77px).

| variant | "después" rendered | visible inside the 691px phone slot |
|---|---|---|
| A — even pair, old order | 170 x 212 | 85px of 212 (40%) |
| B — inset, old order | 340 x 425 | 85px of 425 (20%) |
| D — inset, photo straight after the H1, square on mobile | 340 x 340 | 340px of 340 (100%) |

The inset gives the result **4.01x the area** at both sizes — linear x2.00, which is what
the round-4 critique predicted. What the argument could not predict is that **B was worse
than A on a phone**: a larger picture starting at y=606 inside a 691px slot shows more of
the top of a head and no face at all. Only the screenshot showed that.

So the shape is B's and the order is new:

- On a phone the photograph follows the H1 directly. The old order put 606px of prose —
  subheading, price, IVA line, payment and AI disclosure — in front of the only
  photograph on the page, which is CONVERSION hypothesis 1 inverted.
- **The price moves below the phone slot, and that is deliberate.** "The price is above
  the fold" is now discharged by the header, which is above the fold on every page, not
  by the hero alone. `tests/test_hero.py` asserts the header still carries it, so the
  trade cannot decay into a regression nobody noticed.
- The mobile crop is square: 85px shorter than 4:5, and the thing being sold *is* a
  profile picture, which is square everywhere it will be used.
- The gallery keeps the even pair. There the visitor is comparing and the two images are
  equals; in the hero one is the product and the other is the disclosure.

**Label contrast, found while doing this.** The "Antes" / "Después" labels were
muted-foreground text laid directly on the photograph. Over a photograph a label's
contrast is whatever that photograph happens to be at that corner — unmeasurable, and
different for every pair. They now sit on an opaque paper chip: ink on paper, 16.1:1,
identical on every pair.

### Correction to the paragraph above

The line "the before/after is full-bleed at the top of the first viewport and the divider
is dragged by the visitor" describes something that was never built, and should not be.
A drag divider is a hover-and-drag-only affordance, which `.claude/skills/studioface-ui`
bans outright, and it hides the "antes" behind an interaction on the one element that has
to discharge a legal disclosure. What shipped is the inset: both images visible at once,
no interaction required, the result four times the area of the problem.

### Budgets, measured (18 Sep 2026)

Served from a copy of the real export, gzipped, at 390×844, with **no scrolling at all**.
A transfer budget measured on uncompressed bytes is not a transfer budget, and one
measured after a scroll is not a first-load budget.

| budget | limit | measured |
|---|---|---|
| landing transfer, first load | under 400 KB | **324.1 KB** in 13 requests |
| landing transfer, whole page scrolled | under 500 KB | 465.8 KB in 17 requests |
| LCP timing | under 2.5 s at p75 (web.dev) | 120 ms locally, hero photograph |
| gate wall clock, warm | under 60 s | 9–35 s |
| gate wall clock, cold | under 180 s | 102 s |
| Lighthouse mobile, performance | at least 90 | **98** |
| Lighthouse mobile, accessibility | at least 90 | **100** |
| Lighthouse mobile, best practices | at least 90 | **100** |
| Lighthouse mobile, SEO | at least 90 | **100** |

    transfer total   324.1 KB   (13 requests)
      js             157.0 KB
      fonts           82.8 KB
      images          71.8 KB
      css              6.6 KB
      html + other     5.9 KB

**It was 465.9 KB, and `loading="lazy"` was the reason.** All six photographs were
fetched before the visitor scrolled a pixel; scrolling to the end of a 3763px page then
added *0.0 KB*, which is the proof rather than the symptom. Chromium's lazy-load
distance-from-viewport on a fast connection covers the whole document, so the attribute
is a hint this page never benefits from. The two supporting pairs — 141.7 KB of people
nobody had asked to see — are now held by an IntersectionObserver, which is a mechanism.
After the change, scrolling to the end adds exactly that 141.7 KB back: the same bytes,
moved to the moment they are wanted.

### The LCP element is now the hero photograph, and that is the change

`CLAUDE.md` said the LCP element is the H1 "so there is still no hero image". That was
written when the page had no photographs. It is a proxy, and the thing it was standing in
for is LCP *timing*: Google's threshold is **2.5 s at the 75th percentile**, and the
eligible elements explicitly include `<img>` — nothing requires the LCP element to be text
(web.dev/articles/lcp, verified 18 Sep 2026).

Measured: 120 ms at 390×844, 116 ms at 1440×900. The hero photograph is server-rendered,
eager, sized in the markup, and — since this change — no longer competing with 141.7 KB
of images nobody asked for. Removing that competition does more for it than any priority
hint would.

`fetchpriority="high"` **is** on the hero image, and getting there is worth recording.
It was first rejected because MDN's Baseline badge on that page describes `<img>`, not
the attribute. Lighthouse then scored `lcp-discovery-insight` at 0 and pointed straight
at it, so it was checked properly, against MDN's browser-compat-data rather than a badge:
Chrome 101, Firefox 132, Safari 17.2, standard track, not experimental — and it is a
*hint*, so an older browser ignores it at no cost. Reading the wrong row of the right
source is still answering from memory.

### Lighthouse, mobile, 18 Sep 2026

    Performance      98        largest-contentful-paint     2.4 s
    Accessibility   100        first-contentful-paint       0.8 s
    Best Practices  100        total-blocking-time           60 ms
    SEO             100        cumulative-layout-shift          0
                               speed-index                  0.8 s

No failing binary audit. Performance went 96 → 98 and total blocking time 140 ms → 60 ms
on the priority hint alone.

Two insights are still red and both are read with care:

- `cache-insight`, "est savings of 320 KiB", is an artefact of the measuring harness. The
  local test server sends no cache headers; production serves this export through
  `CachedStatic` in `app/main.py`, which sets `immutable` on everything under
  `/_next/static/` and `no-cache` on the rest. Nothing to fix in the page.
- `unused-javascript`, "est savings of 56 KiB", is the Next.js runtime. Cutting it means
  not using the framework, which is not a design decision to take inside a budget note.

## Motion — five named moments (18 Sep 2026)

Nothing else on this site moves. Every one is triggered by something the visitor did,
none of them loops, and none of them touches anything but `opacity` and `transform`.

| moment | trigger | property | duration | easing | reason |
|---|---|---|---|---|---|
| `sf-frame` | pointer over the upload target | transform | 140 ms | ease-out | The one control that asks for a file should feel like something you can put a thing into. |
| `sf-press` | primary button held | transform | 80 ms | ease-out | On a phone there is no hover, so this is the only tactile confirmation a tap gets before the network answers. |
| `sf-arrive` | the free preview lands | opacity + transform | 300 ms | ease-out | A stranger seeing their own face come back is the most loaded moment in the product, and it used to snap into place. |
| `sf-land` | a delivered photograph replaces its placeholder | opacity | 250 ms | ease-out | Staggered 40 ms per photo, so the fourth still ends at 370 ms and the grid settles rather than flashing. |
| `sf-answer` | an FAQ answer opens | opacity + transform | 180 ms | ease-out | The eye follows the disclosure downwards instead of re-finding the text under the question. |

### The guard, measured rather than read

Parsing the CSS proves the rule was written, not that a visitor who asks for less motion
receives less of it. Chromium was asked for both preferences and the computed styles read
off the live DOM, 18 Sep 2026:

    prefers-reduced-motion: no-preference
      sf-press  on <button>            transform 0.08s
      sf-frame  on the upload target   transform 0.14s
      button held                      matrix(0.98, 0, 0, 0.98, 0, 0)   (:active = true)

    prefers-reduced-motion: reduce
      sf-press  on <button>            all 0.001s
      sf-frame  on the upload target   all 0.001s
      button held                      none                             (:active = true)

The second block is the one that matters: `:active` is still true and the transform is
still `none`. Somebody who has asked for less motion gets **none** of the five moments,
not a fast version of them, because each one lives inside the no-preference query rather
than relying on the global guard to shorten it.

### The ceiling is ours, not a standard

400 ms is a project decision. Material Design 2 and 3 are JS-rendered and could not be
fetched; MDN and web.dev give example values and no normative recommendation. It is
recorded in `docs/verified.md` as explicitly unverified so that nobody later cites it as
an authority. `tests/test_motion.py` enforces it anyway, because the number being ours
does not make it optional.

### What was deleted to get here

`.sf-focus:focus-visible` drew its ring over 220 ms with a `box-shadow` keyframe. Two
rules at once: `box-shadow` is neither opacity nor transform, and — the one that
actually matters — a keyboard user is waiting on that ring to know where they are. The
ring now appears instantly.

`prefers-reduced-motion` is Baseline Widely Available, **across browsers since January
2020** (MDN, verified 18 Sep 2026). The brief said July 2022. The correction matters
here: it means the no-preference query needs no fallback, so a visitor who has asked for
less motion receives none of the five, not a degraded version of them.

# Design decision — 17 Sep 2026

This replaces the previous DESIGN.md, which was a specification with no rationale. It
is a **decision**, and the part that matters is what it refuses.

## What went wrong, measured

`python scripts/design_audit.py frontend/out` against the live build:

    P0  tasteful-default-2026 (cream+serif+sage)  _next/static/chunks/*.css
        var(--font-inter) inter … fraunces … var(--font-geist-mono)
    DESIGN AUDIT: 1 P0, 0 P1, 0 P2   FAIL

One finding, and it is the diagnosis. The old page trips **no** crude tell: no violet
primary, no gradient text, no cardocalypse, no emoji, no "eleva tu marca". It is
Inter + Fraunces + cream `#FAFAF7` + a blue accent `#1D4ED8`, which as of 2026 is the
single most recognisable signature of a page nobody decided. The 3.2M-post analysis
behind claudecodehq.com/playbooks/unslop-ui names exactly this — the "tasteful
default" — as the tell that replaced the purple-gradient era. Restraint stopped being
evidence of taste the moment it became the default output.

A Lighthouse score of 96 and a passing Playwright assertion both sat on top of that.
Neither instrument can see it. That is why the loop now has a deterministic floor
(`scripts/design_audit.py`) and a judge that looks (`.claude/agents/design-critic.md`).

## What we are NOT doing, and why

**Not another restrained neutral page.** The failure mode is not ugliness, it is
averageness, and averageness cannot be fixed by more restraint — more restraint is
what produced it. Every direction below commits to something a cautious page would not.

**Not a SaaS landing page.** Centred hero, three feature cards, a soft shadow and a
blue button is the visual grammar of a dashboard trial. We sell one photograph for
19,99 €. A photography studio's page is dense, image-led and asymmetric; it shows the
work above the fold and explains afterwards. Feature cards are banned outright here.

**Not a trend.** No gradient text, no glassmorphism, no bento grid. These date in
months and they are also, now, tells.

**Not decoration that costs the buyer.** Motion is limited to two named moments, both
tied to something actually happening. The customer is on a phone, possibly on mobile
data, deciding whether to trust us with their face.

### Banned, enforced by scripts/design_audit.py where it can be

Inter, Poppins, Geist, Space Grotesk or Roboto as the only family · any
violet/indigo/purple primary · gradient text · more than one gradient background ·
an untouched shadcn card (`rounded-2xl` + `shadow-lg`) · a coloured 3–4px left border ·
emoji anywhere in the interface · the cream + serif + sage trio · centred hero plus
three cards.

## What every direction must have

| Requirement | Why |
|---|---|
| A type pairing with at least one deliberate family, licence named | The pairing is the loudest single signal of whether anyone chose |
| One dominant colour, one sharp accent, both with hex and a measured contrast ratio | "Dominant plus accent" is a decision; a palette of six is an average |
| An asymmetric primary layout | Symmetry is the default a generator reaches for |
| A spacing scale with a stated ratio | Ad-hoc spacing is the quietest tell of all |
| Motion at no more than two moments, each named | Anything more is decoration |

## The three directions

Built as standalone HTML in `docs/design-variants/`, same copy, different decisions,
so they can be judged against each other rather than against a description.

### A — Cuarto oscuro (darkroom)
Dark, warm, photographic. The page reads as the room the work is made in.

- **Dominant** `#12100E` warm near-black · surface `#1C1917`
- **Accent** `#F0531C` safelight orange — 5.4:1 on the dominant
- **Text** `#F5F2EE` — 16.9:1 on the dominant
- **Type** Bricolage Grotesque (SIL OFL 1.1, Google Fonts) for headlines, Archivo
  (SIL OFL 1.1, Google Fonts) for everything else
- **Layout** 7/5 split, the portrait bleeding off the right edge, the headline
  overlapping it
- **Spacing** 8 · 12 · 18 · 27 · 41 · 61 · 92, ratio **1.5**
- **Motion** (1) the generated photo crossfades in when it arrives; (2) the focus ring
  draws rather than appears

### B — Hoja de contactos (contact sheet)
The physical object a photographer hands you: a sheet of frames, numbered, marked up.

- **Dominant** `#F2F1ED` paper · ink `#141312` — 16.1:1
- **Accent** `#C3352B` film-leader red — 4.81:1 on paper
- **Type** Newsreader (SIL OFL 1.1, Google Fonts) for headlines, Chivo Mono (SIL OFL
  1.1) for frame numbers and labels
- **Layout** 4/8 with a left rail carrying vertical sheet numbering; hard 1px rules,
  no shadows anywhere
- **Spacing** 6 · 12 · 24 · 48 · 96, ratio **2**
- **Motion** (1) the chosen frame lifts on hover; (2) a determinate progress rule
  during generation

### C — Carné (high-contrast studio)
White, oversized type, one saturated accent. The booth, modernised.

- **Dominant** `#FFFFFF` · ink `#0B0B0B` — 19.6:1
- **Accent** `#00706B` deep teal — 5.1:1 on white
- **Type** Archivo Black (SIL OFL 1.1) for the headline, Public Sans (SIL OFL 1.1) for
  body
- **Layout** headline set hard to the left edge across two columns, the sample
  photograph pushed to the lower right, deliberately unbalanced
- **Spacing** 8 · 16 · 24 · 40 · 64 · 104, ratio **1.618**
- **Motion** (1) the headline settles on load, once, 240ms; (2) the upload target
  responds on drag-over

## Copy and commercial rules (unchanged, they were never the problem)

Spanish es-ES, tú form, prices `19,99 €` IVA incluido, no exclamation marks, no
superlatives. H1 contains "foto de perfil profesional" (Google Ads). Price above the
fold. LCP element is the H1, not an image. Footer links to Aviso legal, Privacidad,
Términos, Cookies — **and to /recuperar/**, which existed with nothing linking to it.

Imagery: real before/after pairs only. Until Kevin supplies them (issue #6) the page
shows one honest sample area saying an example will appear here. **It must not fake a
result**, and the critic scores line 5 down for the absence rather than being fooled.

## Sources for the slop catalogue

vibecodekit.dev/ai-slop-design · 925studios.co/blog/ai-slop-web-design-guide ·
claudecodehq.com/playbooks/unslop-ui (3.2M-post Reddit analysis; its top 2026 tell is
the cream+serif+sage "tasteful default") ·
sailop.com/blog/ai-slop-2026-state-of-the-ai-generated-web ·
github.com/funboy322/avoid-ai-design. All accessed 17 Sep 2026.

## Decision

**B — Hoja de contactos ships.** Round 1 scored A 34/50 (FAIL), B 40/50, C 37/50.

A was disqualified by a bug, not by taste: at 1440×900 its H1, price and CTA all sat
below the fold, because the frame's negative-margin bleed made it ~775px tall at that
width and `align-items:end` dragged the text column down with it — breaking this
document's own "price above the fold" rule. The floor passed it, every unit test passed
it, and Lighthouse would have too.

**What choosing B costs.** Its distinguishing device is monospace, and monospace running
copy reads as a technical document to a buyer deciding whether to trust a stranger with
their face. That risk was real enough that the first implementation pulled body prose
back onto Public Sans and kept mono for frame numbers and labels only — which spends
some of the distinctiveness B was chosen for. If conversion copy ever leans on that
voice, test it with real users first.

**Loop record.** Round 1 (mocks) B 40/50 → round 2 (real pages) 32/50 → round 3 39/50.
Round 2 fell because only one of seven routes had actually been redesigned: the tokens
are CSS variables and did inherit, but `--font-fraunces` had been *deleted*, so six
routes fell back silently to body weight. An undefined CSS variable is not an error.
Neither the suite nor the floor can see that; one screenshot could.

**The target is not reachable yet, and that is the honest stopping point.** Rubric line
5 — is the product's value visible above the fold — is capped at 2 while we show no real
photographs, so "no line below 3" fails on arithmetic regardless of every other line.
It unblocks with issue #6 (Kevin's own before/after pairs and his written consent).
Issue #3 (legal entity name) is worth roughly +1 each on lines 6 and 10. Full rubrics in
docs/design-review/.
