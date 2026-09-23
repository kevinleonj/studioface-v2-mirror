# Google Ads campaign — StudioFace

Source of truth for ad copy is `docs/ads/rsa.json`, validated by `scripts/check_ad_copy.py`
(character limits, one duplicate check per group) and `scripts/check_ad_claims.py` (every
number or duration an ad promises must appear on the landing page it points to). No campaign
and no ad group is created in the Google Ads account by this document or by those scripts —
they only write and check files.

The "Live account state" section below records the campaign as it exists in the Google Ads
account, built on 23 September 2026 through the Google Ads API. Nothing in this repository
creates, edits or enables anything in Google Ads; this document and those scripts only write
and check files. When the account changes, this section changes in the same commit.

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
  below) or Kevin says otherwise. The live campaign below is the `cv` group only —
  `linkedin` is not part of it.

## Live account state (built 23 September 2026)

Built through the Google Ads API (Windsor) on 23 September 2026, not by hand. `rsa.json` is
the source of truth for every keyword, headline and description; this section records the
settings that only exist in the account.

| Setting | Live value |
|---|---|
| Campaign | Search campaign `StudioFace CV 2026-09`, id `24285475822` |
| Created | via the Google Ads API (Windsor), 23 September 2026 |
| Status | **PAUSED** until Kevin enables it; it serves nothing before that |
| Bidding | Maximize clicks, maximum cost-per-click bid limit 1,20 EUR |
| Budget | 5 EUR per day |
| Dates | 23 September to 2 October 2026 |
| Locations | Spain, presence only |
| Language | Spanish |
| Networks | Google Search only (no Search Partners, no Display) |
| AI Max | off |
| Broad match | off |
| Automatically created assets | off |
| Auto-tagging | on |
| Auto-apply recommendations | off |

**Ad group `cv`**, final URL `https://studioface.app/foto-cv/`, the 4 exact-match keywords
in `rsa.json`'s `keywords_exact`. Its ad is the `cv` group's own headlines and descriptions
in `rsa.json`. A second ad, `cv-b`, is in `rsa.json` under `additional_ads` (task 95j) and
is created in the account after that change merged.

**Negative keywords**, campaign level, phrase match: 41, exactly `rsa.json`'s
`negative_keywords_phrase` (the original 40 plus `gratis`).

**Sitelinks**

| Sitelink | Final URL |
|---|---|
| Foto para LinkedIn | https://studioface.app/foto-linkedin/ |
| Cómo funciona | https://studioface.app/ |
| Condiciones de compra | https://studioface.app/legal/terminos/ |
| Borrado en 7 días | https://studioface.app/legal/privacidad/ |

**Callouts**, exactly as live: `Prueba gratis`, `Sin registro`, `Pago único, IVA incluido`,
`Listo en dos minutos`.

**Not recorded here:** the campaign's conversion goal. The old build sheet specified
**StudioFace (web) purchase** as the only primary conversion action; the live state above
does not include it, so check it in the account rather than trusting this file.

### Daily budget versus the first step — read this before setting either

A daily budget of 5 EUR against the 50 EUR first step (see Pre-registered test below)
means the step lasts about **ten days** if it spends out every day (50 divided by 5).
Google Ads is allowed to spend up to double the daily budget on any single busy day and
less on a quiet one, so one day's spend column can show more than 5 EUR — that is normal
pacing, not an error. **What governs is the 50 EUR step cap, not the number of days.**
Check total spend against 50 EUR (via the Google Ads spend column, or
`scripts/funnel_report.py`), not the calendar — do not wait for day ten to look.

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

- **Bidding strategy and daily budget are decided and live** (Maximize clicks, 1,20 EUR
  maximum cost-per-click bid, 5 EUR a day): see "Live account state" above.
- **The retention disclosure gap is closed.** Task 33 put "¿Qué pasa con mis fotos?" on
  both ad landing pages, so "7 días" in the ads is stated on the page they point to;
  `scripts/check_ad_claims.py` passes and its test is no longer marked xfail.
- **Enabling the campaign** is Kevin's action in the account. Nothing here does it.
