# The free-preview limit and the reload, tested by hand — 22 September 2026

An automated attempt at this ran for over two hours and produced nothing, because
production's human check is the real Cloudflare widget, not the always-pass test key the
local browser tests use, and a script cannot solve it. So this test was run by a person in
a real browser. What follows is what he saw, not what a test asserted.

## What was run

A fresh private window on https://studioface.app, his own photo, between 13:04 and 13:09
UTC on 22 September 2026. Three free previews spent, then a fourth attempt, then a real
page reload. Nothing that opens Stripe was pressed. About 0,36 US dollars of image
generation.

## What happened

The limit path works.

- Three previews returned 200, at 13:04:39, 13:07:00 and 13:07:46.
- The fourth attempt returned 200 in one second — no image was generated, which is the
  storage-only path doing exactly what it was built to do — carrying the sentence
  "Has usado tus pruebas gratis de esta hora. Puedes comprar tus cuatro fotos ahora o
  volver dentro de una hora." and an **enabled** buy button.

The reload path fails.

After a real reload (`location.reload`, page loaded 13:08:55):

- One re-sign call to `/api/preview/{batch}` went out, and **no new preview request** —
  so the stored handle was found and honoured, and the reload cost the visitor nothing.
  That half works.
- But the buy button rendered **disabled**.
- The dropzone had gone back to "Sube de 1 a 4 selfies".
- Zero thumbnails, no preview picture, and no limit sentence.

## What this means

A visitor who has used their three free previews, is shown a working buy button, and then
reloads the page — or comes back to the tab later — loses the ability to buy, even though
the server still holds their photos and the handle is still valid. The page forgets the
count of stored photos on reload, and the buy button is disabled whenever it thinks no
photos are chosen. The sale is lost to a page refresh.

This is the same shape as the defect found on 21 September, where a visitor at the limit
had no buy button at all: the server is right and the page is wrong.

RESULT: limit path works, reload path fails at the limit

The fix is task 55, reload-keeps-the-sale, which restores the stored photo count, the
picture when there is one, the limit sentence, and an enabled buy button after a reload.
This file records what was observed and is not updated to claim both paths work until a
person sees both paths work.

## Addendum, same day, after the fix

Task 55 fixed what this test found, and it is deployed. The page now remembers, across a
reload, that the free tries were spent and how many photos the server is holding, so the
limit sentence comes back, the count comes back, and the buy button is enabled and sells
that stored batch. A browser test proves it end to end with the image model faked: reach
the limit, reload, then press buy and read the request the button actually sends, checking
the batch, count and signature are the stored handle's own and not an empty or fresh one.
The guard that refuses to sell an empty set when a visitor removes every photo by hand
still passes, with its own test, so the fix did not weaken it. Twenty browser tests pass.

RESULT above stays as it is. It records what a person saw on 22 September, and the honest
way to change it is for a person to look again, not for a test to vouch for the page on
his behalf. The one thing worth re-checking by eye, whenever convenient and at the cost of
three more free previews: reach the limit, reload, and confirm the sentence, the count and
an enabled buy button are all there.
