# Task 20: who is the visitor — measuring the `visitor_address` inference

## Why this exists

The per-visitor preview cap (3/hour) and the `/api/recuperar` cap both key on
`visitor_address(x_forwarded_for, request)`, which (since task 14) trusts the
LAST entry of `X-Forwarded-For`. That was an inference from the documented
single-hop ingress path (Client -> Google Front End (GFE) -> this container,
docs/verified.md 13c), never measured against a real request. If it were
wrong — if the LAST entry were GFE's own address rather than the visitor's —
every visitor would share one rate-limit key and the site would cap out at
3 previews an hour total under ad traffic. This is checked before any ad
spend starts.

## Method

Cloud Run keeps two separate log streams for this service:

- `run.googleapis.com/requests` — Cloud Run's own record of each request,
  carrying `httpRequest.remoteIp`: the real TCP peer address GFE observed,
  not something the app or a visitor can influence.
- `run.googleapis.com/stdout` — whatever the app itself writes.

Before this task, the app never logged the raw `X-Forwarded-For` header, so
the two streams could not be compared. Per the task's fallback plan:

1. Added `xff_shape(x_forwarded_for)` in `app/main.py`, called from
   `visitor_address` on every request. It logs one INFO line with the
   **number of entries**, and the **first two octets** of the first and last
   entry (never a full address) — enough to line up against Cloud Run's own
   `remoteIp` (also read here only to its first two octets) without ever
   writing a visitor's full IP anywhere.
2. Failing test first (`tests/test_visitor_address.py`): `xff_shape` did not
   exist -> `NameError` collecting the module. After implementing it,
   `13 passed` (4 new cases: multi-entry, single-entry, non-IPv4 entry,
   empty header).
3. `.venv\Scripts\python.exe scripts\ci.py` green, merged to main
   fast-forward, pushed with `git push origin main`.
4. Watched the deploy: GitHub Actions run `35581370804`, all jobs green,
   `gh run watch 35581370804 --exit-status` exited 0. Deployed revision
   `studioface-api-00139-tb8`, serving 100% of traffic (confirmed via
   `gcloud run services describe`).
5. Made two harmless requests against production myself, immediately after
   the deploy finished, and read both log streams back, correlating by the
   exact trace id each response returned in its `x-cloud-trace-context`
   header (so this is not a timestamp guess — it is the literal same
   request in both logs). Both cost nothing and sent no email:
   - Request A: `POST /api/recuperar` with a hand-crafted
     `X-Forwarded-For: 198.51.1**.9, 203.0.1**.42` (two fake, prepended
     entries — the exact attack task 14 closed). The email address does not
     exist in the store, so `find_by_email` returns nothing and no email is
     sent; response was `{"sent":true}`, HTTP 200 (recovery emails always
     answer the same way, by design, whether the address exists or not).
   - Request B: `POST /api/preview` with an invalid Turnstile token and no
     custom header at all (the natural case). `visitor_address` runs before
     the Turnstile check, so the log line fires; the request is then
     rejected with HTTP 403 before any file is read or any fal call is made.

## Evidence (pasted, IPs truncated to first two octets everywhere)

**Cloud Run's own request log** (`run.googleapis.com/requests`), the two
requests I made, found by their trace id:

```
2026-09-21T09:13:46.938381Z  POST /api/preview    remoteIp=77.225.*.*  403  trace=bbcc31c2bba16d07b366dfd3cd143e27
2026-09-21T09:13:37.878196Z  POST /api/recuperar   remoteIp=77.225.*.*  200  trace=b74807b65d0027cba7403277c2bca264
```

**The app's own stdout log** (`run.googleapis.com/stdout`), the new
`xff_shape` line, same two requests, matched by the same trace id:

```
2026-09-21T09:13:47.000200Z  visitor_address xff shape=entries=1 first=77.225 last=77.225 first_eq_last=True   (request B, trace bbcc31c2bba16d07b366dfd3cd143e27)
2026-09-21T09:13:37.894107Z  visitor_address xff shape=entries=3 first=198.51 last=77.225 first_eq_last=False  (request A, trace b74807b65d0027cba7403277c2bca264)
```

**The comparison that answers the question**, request A: I sent a header
with 2 entries (`198.51.*.*, 203.0.*.*`, both fake, both mine). The app
received **3** entries — GFE appended one more on top of what I sent, it did
not replace or leave the header untouched. The LAST entry's first two octets
(`77.225`) match `httpRequest.remoteIp`'s first two octets (`77.225.*.*`)
for the exact same request, read from the exact same trace id. My two fake,
attacker-controlled entries occupy positions 1 and 2; GFE's own, unforgeable
entry is position 3, the last one.

Request B (no header sent by me at all) shows the baseline: GFE sets exactly
one entry, and it equals `remoteIp`, confirming the single-hop assumption
(GFE is the only hop) holds for the ordinary case too.

**Prior organic traffic**, for context on real-world diversity (not usable
for the header comparison itself, since the app did not log the raw header
before this deploy so there is nothing on the stdout side to correlate
against): `/api/preview` and `/api/recuperar` had real `POST` traffic from at
least three distinct real client addresses in the last two weeks (`77.225.*`,
`178.139.*`, `2.138.*`), plus a long tail of bot `GET` probes against
`/api/preview` returning 405 from dozens of distinct addresses — those never
reach the FastAPI handler (Starlette returns 405 before the route function
runs), so they never call `visitor_address` and carry no evidence either way.

## RESULT

**RESULT: last entry is the visitor's real, GFE-appended address — it
matches Cloud Run's own `httpRequest.remoteIp` for the same request, even
when I prepended two fake entries myself.** The current code
(`x_forwarded_for.split(",")[-1]`, unchanged since task 14) is correct. No
code change was made to `visitor_address`'s selection logic — only the new
`xff_shape` observability line was added, which is what made this
measurement possible.

**How certain.** This is a direct, trace-correlated measurement against live
production traffic through the real GFE -> Cloud Run path every visitor
uses, not an inference: both the app's own log and Cloud Run's independent
request log agree, for the same request, identified by the same trace id,
with the fake entries clearly separated from the real one because I
controlled what I sent. I am confident the LAST entry is correctly keyed and
the per-visitor cap is not shared by every visitor. What I did not do: watch
this hold across dozens of distinct real visitor addresses simultaneously
(only two requests, both from my own network, one deliberately adversarial)
and across a longer time window or a second Cloud Run region/instance. That
is a narrower gap than "unmeasured inference" was, but it is not a
week of production traffic. Given the mechanism is GFE's own documented
single-hop proxy behaviour (docs/verified.md 13c) and the one adversarial
case I constructed produced exactly the predicted result, I would not
withhold ads on this account.

## Not verified

- Whether GFE ever appends more than one entry, or zero, under some request
  shape I did not try (e.g. an already very long header, or a request
  routed through some other Google edge product) — not observed.
- Whether this holds identically for every Cloud Run region/instance the
  service could scale to — only the currently live revision and instance
  were exercised.
