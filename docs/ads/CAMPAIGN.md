# Google Ads campaign — StudioFace

Source of truth for ad copy is `docs/ads/rsa.json`, validated by `scripts/check_ad_copy.py`
(character limits, one duplicate check per group) and `scripts/check_ad_claims.py` (every
number or duration an ad promises must appear on the landing page it points to). No campaign
and no ad group is created in the Google Ads account by this document or by those scripts —
they only write and check files.

The "Building the CV campaign in Google Ads" section below is the field-by-field sheet Kevin
builds the campaign from by hand. It names every field the way Google Ads names it on screen.
Nothing in this document touches Google Ads; the campaign is built by a human reading this file.

## Settled

- **Search only.** Google Search, no Search Partners, no Display. `rsa.json`'s
  `campaign.type` / `campaign.networks`.
- **Location: Spain. Language: Spanish.**
- **Exact match only**, on both ad groups' `keywords_exact` — no phrase or broad match.
- **Two ad groups**, matching the two landing pages built in task 23:
  - `cv` -> `https://studioface.app/foto-cv/`, keywords around "foto curriculum" / "foto cv".
  - `linkedin` -> `https://studioface.app/foto-linkedin/`, keywords around "foto linkedin".
- **Negative keyword list at campaign level** (`negative_keywords_phrase` in `rsa.json`,
  phrase match): free/generic-AI-tool traffic (`free`, `midjourney`, `chatgpt`, `canva`,
  `photoshop`, `prompt`, `app`, `apk`...), unrelated-photo traffic (`carnet`, `dni`,
  `pasaporte`, `boda`, `quitar fondo`...), and document/template traffic (`plantilla`,
  `word`, `pdf`, `cv con foto`...).
- **First-step cap: 50 EUR.** `campaign.total_cap_eur` in `rsa.json` records this same
  number. It is the first of the three 50 EUR steps of the 150 EUR pre-registered test
  below, not a separate budget — the pre-registered test is what governs, not this bullet.
- **The `cv` group goes first.** It stays the only group serving until it has either hit
  its own share of the first step's spend or been paused; `linkedin` starts only after `cv`
  has produced a signal (a preview started or a sale, per the pre-registered kill rule
  below) or Kevin says otherwise. The campaign built below is the `cv` group only —
  `linkedin` is not part of it.

## Building the CV campaign in Google Ads

> **Pause it the moment it is saved.** Google Ads starts serving ads as soon as a campaign
> is created and left enabled, and there is no way to create it already paused. The very
> first thing to do after clicking Save is: go to **Campaigns**, tick the checkbox next to
> the new campaign's name, click **Edit**, click **Pause**. Do this before doing anything
> else, before checking the ad preview, before going to make coffee. This instruction is
> repeated at the end of the checklist below — do not skip either copy of it.

Everything in this section comes from `docs/ads/rsa.json`'s `cv` ad group, copied character
for character, plus the decisions below that are Kevin's own (bidding and daily budget).

### Campaign settings

| Field, as Google Ads names it | Value |
|---|---|
| Campaign name | `StudioFace CV 2026-09` |
| Campaign type | Search |
| Results you want / goal | No goal's guidance — build it without a campaign objective |
| Networks | Search Network only. Leave **Include Google Search Partners** unticked. Do not include the Display Network. |
| Locations | Spain |
| Languages | Spanish |
| Bidding | **Maximize clicks.** Tick **Set a maximum cost per click bid limit** and enter **1,20 EUR**. (Kevin's decision.) |
| Budget | Daily budget: **5 EUR** |
| Ad group name | `cv` (only ad group in this campaign) |

### Keywords (ad group `cv`, exact match)

Add each one exactly as written, including the square brackets — the brackets are what
tells Google Ads this is exact match:

```
[foto curriculum]
[foto cv]
[foto para curriculum]
[foto de curriculum]
```

### Negative keywords (campaign level, phrase match)

Add on the campaign's **Negative keywords** page, not inside the ad group. Set the match
type to **Phrase match** for every line (or wrap each one in quotation marks when typing
it in, which sets phrase match directly). All 40, copied from `rsa.json`'s
`negative_keywords_phrase`, unchanged:

```
gratis online
free
generador de imagenes
crear imagenes
dibujo
anime
avatar
logo
fondo de pantalla
midjourney
chatgpt
gemini
canva
photoshop
prompt
app
apk
descargar
fotografo
estudio fotografico
boda
carnet
dni
pasaporte
quitar fondo
mejorar calidad
restaurar foto
video
plantilla
word
pdf
ejemplo
sin foto
tamaño
medidas
fondo
portada
cv con foto
pinterest
meme
```

### The ad (responsive search ad, ad group `cv`)

**Final URL:** `https://studioface.app/foto-cv/`

**Path fields** (the two boxes under the final URL that build the display path):
- Path 1: `foto-cv`
- Path 2: `gratis`

**Headlines** — Google Ads gives 15 headline boxes; only the first 12 are filled, the rest
stay empty. Copied character for character from `rsa.json`, each one already checked
against Google's 30-character headline limit by `scripts/check_ad_copy.py`:

| Headline | Characters |
|---|---|
| Foto para tu CV con IA | 22/30 |
| Prueba gratis, sin registro | 27/30 |
| Tu foto de currículum lista | 27/30 |
| Foto de CV en dos minutos | 25/30 |
| Sin fotógrafo ni estudio | 24/30 |
| Paga solo si te gusta | 21/30 |
| 4 fotos para CV por 19,99 € | 27/30 |
| Hecha con tus propios selfies | 29/30 |
| Pago único, IVA incluido | 24/30 |
| Mira el resultado antes | 23/30 |
| Foto profesional para el CV | 27/30 |
| StudioFace: fotos con IA | 24/30 |

**Descriptions** — Google Ads gives 4 description boxes; all 4 are filled. Copied
character for character from `rsa.json`, each already checked against Google's
90-character description limit:

| Description | Characters |
|---|---|
| Sube de 1 a 4 selfies y mira una prueba gratis. Sin registro y sin tarjeta para probar. | 87/90 |
| Cuatro fotos profesionales para tu currículum por 19,99 €, IVA incluido. Pago único. | 84/90 |
| Cambiamos la luz, el fondo y la ropa, no tu cara. Compruébalo gratis antes de pagar. | 84/90 |
| Tus fotos se borran a los 7 días. Si no generamos las cuatro, devolución automática. | 84/90 |

### Conversion goal

In the campaign's **Goals** settings, set the campaign to use a campaign-specific
conversion goal, and select **StudioFace (web) purchase** as the only primary conversion
action for this campaign. Nothing else should be ticked as primary.

### Daily budget versus the first step — read this before setting either

A daily budget of 5 EUR against the 50 EUR first step (see Pre-registered test below)
means the step lasts about **ten days** if it spends out every day (50 divided by 5).
Google Ads is allowed to spend up to double the daily budget on any single busy day and
less on a quiet one, so one day's spend column can show more than 5 EUR — that is normal
pacing, not an error. **What governs is the 50 EUR step cap, not the number of days.**
Check total spend against 50 EUR (via the Google Ads spend column, or
`scripts/funnel_report.py`), not the calendar — do not wait for day ten to look.

### Checklist — tick each one while building the campaign by hand

- [ ] Campaign type set to Search, no goal-guided flow
- [ ] Campaign name set to `StudioFace CV 2026-09`
- [ ] Networks: Search Network only, Search Partners unticked, Display not included
- [ ] Location set to Spain
- [ ] Language set to Spanish
- [ ] Bidding set to Maximize clicks, with a maximum cost-per-click bid of 1,20 EUR
- [ ] Daily budget set to 5 EUR
- [ ] Conversion goal set to **StudioFace (web) purchase** as the sole primary conversion
- [ ] Ad group `cv` created (only ad group — `linkedin` is not built yet)
- [ ] All four exact-match keywords added, each inside square brackets
- [ ] All 40 negative keywords added at campaign level, all set to phrase match
- [ ] Final URL set to `https://studioface.app/foto-cv/`
- [ ] Path 1 set to `foto-cv`, Path 2 set to `gratis`
- [ ] All 12 headlines entered, character for character from the table above
- [ ] All 4 descriptions entered, character for character from the table above
- [ ] Campaign saved
- [ ] **Immediately after saving: Campaigns, tick the campaign's checkbox, Edit, Pause —
      done before anything else**

## Pre-registered test

Written 2026-09-22, before any campaign exists in the Google Ads account — so these
numbers cannot be adjusted after seeing how the campaign performs.

Budget 150 EUR total, released in three steps of 50 EUR. Step 1 stops after 50 EUR or
14 days, whichever first. Kill after step 1 if clicks from Google Ads are fewer than
25, or previews started are fewer than 1 in 10 clicks, or paid orders are zero.
Continue to step 2 only if cost per paid order projects under 20 EUR (spend divided by
paid orders). Kill after step 3 if cost per paid order is above 11,99 EUR or paid
orders are fewer than 8. Arithmetic shown: at 1,20 EUR a click, 50 EUR buys about 42
clicks; 4 percent buying gives 1 to 2 orders and 8 percent gives 3 to 4, so step 1 can
only tell 'zero' from 'some'; the 4-versus-8 percent question needs all 150 EUR, about
125 clicks. The numbers 1,20 EUR and 4 to 8 percent are labelled estimate; the click
price comes from Google Keyword Planner on 20 September 2026 and the buy rate has
never been measured at 19,99 EUR.

`scripts/funnel_report.py` (task 46) is what reads the previews-started and
paid-orders numbers this rule needs, from Firestore and the app's own records — read
only, no campaign is created or touched by it.

This is the rule that governs the campaign, replacing the older single-step 50 EUR stop
rule that used to be written out in full in this file. That original wording is not
repeated here — it is preserved in git history and in `HANDOFF.md`'s 21 September 2026
entry for task 33, which is where it was first written. Keeping only one kill rule in this
file, instead of two, is what stops this document from showing two different budgets as if
both were still live.

## Open — Kevin decides

- **Bidding strategy and daily budget are now decided** (this task, 2026-09-22): Maximize
  clicks with a 1,20 EUR maximum cost-per-click bid, 5 EUR daily budget — see "Building the
  CV campaign in Google Ads" above for the exact fields. They are no longer open.
- **The retention disclosure gap.** `scripts/check_ad_claims.py docs/ads/rsa.json
  frontend/out` reports, for both groups: `claim '7 días' not found on
  frontend\out\<slug>\index.html`. Both ad groups' descriptions say "Tus fotos se borran a
  los 7 días" (true — it is stated on the home page FAQ, in the delivery email, and in
  `/legal/privacidad/`), but the ad-landing pages built in task 23 show only 3 of the
  5 shared FAQ questions (`frontend/src/content/ad-pages.ts`, `SHARED_FAQ`), and the
  retention question is not one of the three. This task did not touch that file — it
  was not asked to, and it is live, real-payments copy. Kevin decides: add the retention
  question back to the two ad-landing pages, or drop the "7 días" line from the ad
  descriptions. `tests/test_check_ad_claims.py::test_the_real_ad_groups_claims_do_land_
  on_their_pages` is marked `xfail(strict=False)` for exactly this reason, so it stays
  visible in every pytest run without blocking `scripts/ci.py`.
