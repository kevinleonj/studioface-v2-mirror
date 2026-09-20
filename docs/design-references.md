# Design references — three pages, measured at the true fold

Written 18 September 2026. Asked for three times and not written until now.

**Nothing here is copied.** Each page was loaded in a real browser at 390×844, the fold
was measured rather than assumed, and what sits inside that fold was extracted in document
order. The value is in the *structure* — what a page spends its first screen on — and in
the numbers, not in the look.

## The method, and why it is not "screenshot three sites"

A screenshot at 390×844 is a screenshot of a page nobody sees. **The usable slot is the
viewport minus whatever is pinned to the bottom**, and every site has different furniture
there. So the script finds every `fixed` or `sticky` element whose bottom touches the
viewport floor, takes the highest one, and treats *its* top as the fold. Measured:

| page | viewport | **real fold** | what eats the difference |
|---|---|---|---|
| linear.app | 390×844 | **844** | nothing pinned |
| basecamp.com | 390×844 | **761** | a 205×83 element at y=761 |
| aragon.ai | 390×844 | **844** | nothing pinned |
| **studioface.app** | 390×844 | **691** | the consent banner, 153px |

**We have the smallest first impression of the four, by a wide margin**, and it is
self-inflicted: 153px of the 844 goes to a cookie banner, against Basecamp's 83 and
Linear's nothing. That is 18% of the screen spent before the product says anything. It is
also the cheapest thing on this page to win back — see the banner note at the end.

## linear.app — a type system that is one decision

    h1  38px / weight 510 / Inter Variable / line-height 41.8px / tracking -0.836px
        343×167 at y=196, 38 images, document 5876px, no price above the fold

The number worth stealing is **-0.836px of tracking on a 38px headline**, which is
-0.022em. Ours is `tracking-[-0.02em]` on a `clamp(38px, 6.4vw, 68px)` H1 — the same
decision, arrived at independently, and it is reassuring rather than surprising: at that
size, unadjusted tracking looks loose and everyone who cares converges there.

Weight **510** is the interesting one. Not 500, not 600 — a variable-font weight chosen
between the two static ones that most systems offer. It is a small proof that their type
is a decision rather than a default, which is exactly the property `design_audit.py`
exists to detect the absence of.

What their first screen contains: the H1, one 276×48 subhead, and then *the product
itself* — a working replica of the Linear sidebar, rendered in DOM, `Pulse / Inbox / My
issues / Reviews / Workspace / Initiatives / Projects`. No photograph, no testimonial, no
price. **They lead with the artefact.** Ours cannot — a headshot service's artefact is a
photograph of a person, which is why the inset hero is the right analogue and why it
belongs directly under the H1 rather than after the price.

## basecamp.com — the shortest distance to a demonstration

    h1  30px / weight 600 / Graphik / line-height 34.5px / tracking -0.675px
        346×173 at y=76, 20 images, document 5672px

The H1 starts at **y=76**. Ours starts at y=151, because our header is 119px tall against
their ~45. They buy that by putting the nav links in a row that starts at y=33 and is
193px wide — a stack of seven small links — rather than a wordmark row plus a wrapped nav
row. It is a real cost and worth knowing: **68px of our first screen is header chrome we
chose.**

The structure inside their fold, in order: sign-in links, seven nav links, the H1, then a
**336×64 button reading "Take a 3 minute tour of Basecamp"** with a 99×56 thumbnail
beside it. A 64px-tall button — well above the 44px floor — and its label promises a
duration. That is the same move as our "Suele tardar unos dos minutos" on the wait screen,
applied to the *ask* rather than to the wait. Worth considering for the preview CTA: "Ver
una prueba gratis" says what, not how long.

Their H1 is a full sentence, 30px, three lines, 173px tall. Ours is 38px and 116px tall.
Neither is wrong; theirs buys the space for the demonstration button to sit inside the
fold, ours buys presence. We have the photograph to justify the presence; they do not.

## aragon.ai — the direct competitor, and the most instructive of the three

    h1  28px / weight 700 / Plus Jakarta Sans / line-height 40px / tracking -1.5px
        350×80 at y=130, 635 images, one video, document 4228px

The structure of their first screen is the thing to read, because it is the same funnel:

    h1@130    "Der beliebteste KI-Porträtfoto-Generator"
    p@210     "Sparen Sie sich den Fotografen für 500 $. ..."
    a@334     "Erstellen Sie jetzt Ihre Porträtfotos."     345×58, the CTA
    a@472     "4.8"      a@476  "4.9"                      review scores
    img@528   "Before: Headshot example 1"   142×178
    img@528   "After: AI-enhanced Headshot example 1"      142×178

Three things, in order of how much they should change our thinking:

**1. Their before/after is 142×178 and arrives at y=528.** That is *smaller than the
170×212 pair we just replaced*, and it sits below the CTA and below the review badges.
They are betting the claim sells and the proof merely reassures. We have bet the opposite
— 340×340 at y=292, the proof before the price. Ours is the better bet for a product with
no brand and no review count, and the measurement makes that a choice rather than an
accident. It is also the one place I would not follow a competitor.

**2. They anchor the price against a photographer, not against zero.** "Sparen Sie sich
den Fotografen für 500 $" — save yourself the 500-dollar photographer. The number in the
first screen is the *alternative's* price, not theirs. We put "19,99 € IVA incluido" in
the header and nothing to compare it to. A Spanish professional's reference price for a
session with a photographer is not something I can assert from here, so this is a
hypothesis for `docs/CONVERSION.md` rather than a copy change: **H8 — an anchor against
the cost of a photo session raises `upload_start / view_proof`.** It needs a verified
Spanish market figure first; inventing one would be a misleading comparison under
Directive 2005/29/EC, which is the same law our synthetic-people disclosure answers.

**3. 635 images on one page**, against Linear's 38 and Basecamp's 20. Their document is
4228px and carries a wall of sample faces. It is the opposite of our three pairs, and I do
not think it is better — but it does say that our *two* deferred pairs are conservative,
and if the real-order muestras (issue #6) produce more, the page has room.

Their tracking is **-1.5px on 28px**, which is -0.054em — over twice Linear's ratio and
visibly tight. Recorded because it is a live example of a decision that could equally be
read as a mistake; without their reasoning I am not copying it either way.

## What I would change here, in order

1. **The consent banner costs 153px of 691.** Nothing else on this list is close to that
   as a lever. See the separate note in HANDOFF: reject-all parity is required, a large
   banner is not.
2. **The header costs 68px more than Basecamp's.** It wraps to three rows at 390 because
   four items do not fit one. A single row — wordmark left, price right, the two links
   below only if they do not fit — would return roughly 55px to the first screen.
3. **The CTA could promise a duration.** Basecamp's button says three minutes. Ours says
   "Ver una prueba gratis" and the time is only mentioned later.
4. **The price has nothing to compare it against.** Aragon anchors on a photographer.
   Filed as H8 in `docs/CONVERSION.md`, blocked on a verifiable Spanish figure.

## What I deliberately did not take

- Linear's product-replica hero. Our artefact is a face, not an interface.
- Aragon's small, late before/after. Measured, it is smaller than the one we replaced for
  being too small, and they have review counts to lean on that we do not.
- Any typeface, colour, spacing scale or piece of copy from any of the three.

Screenshots and the raw measurements are in the session scratchpad rather than the repo:
they are third-party pages, and committing them would put someone else's design in our
history for no benefit that the numbers above do not already give.
