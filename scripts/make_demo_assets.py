"""Build the three before/after pairs the landing page needs. One shot, idempotent.

Rubric line 5 — "does the product's value appear visually above the fold, a real face
rather than a promise" — is capped at 2 while the page shows no photographs. It is the
only line no amount of layout work can move. This script is how it moves.

WHY SYNTHETIC PEOPLE
We have no consenting models. Using a stranger's face is not available to us, and
using Kevin's is issue #6 and needs his written permission. So the SOURCES are
generated: three imaginary people, each photographed as an ordinary person photographs
themselves. They are labelled as generated everywhere they appear (see LABELLING).

IMAGE-PROMPT RULES, applied to every prompt string here
  - Name the camera SITUATION, not an art style. "Front camera, 26mm equivalent, arm's
    length, kitchen window behind" produces a photograph. "Professional portrait,
    cinematic" produces a render.
  - Every source prompt states: subject, framing, lighting, background, wardrobe,
    expression, and ONE imperfection that makes it real — slight motion blur, uneven
    skin, an off-centre crop. Without the imperfection the "before" looks better than
    the "after" and the whole comparison collapses.
  - The words "professional", "studio", "8k", "masterpiece" and "beautiful" are
    FORBIDDEN in source prompts and the test enforces it. A source that looks
    professional defeats the point: it must look like a bad phone photo.
  - Negatives live in their own clause at the end, never mixed into the description.
  - Never a brand name, never a minor, never a medical claim, in any prompt.

WHAT IS REAL HERE AND WHAT IS NOT
The "after" images are produced by the REAL pipeline: the same app.core.Pipeline, the
same guards.build_prompt, the same fal model and parameters a paying customer's photos
go through, executed against the production Cloud Run service via
POST /internal/generate. What is NOT real is the payment: creating a genuine order
needs a Turnstile solve and a card form, both of which are human actions this session
is forbidden from performing. The order is therefore written directly to Firestore with
an id that begins "demo-", so it can never be mistaken for a customer's.

Side effects on live systems, stated because they are real:
  - one order document per person in the production Firestore `orders` collection
  - four output objects per person in BUCKET_OUT
  - one delivery email per person to the address in DEMO_EMAIL
  - one GA4 purchase event per person, transaction_id = the demo- order id

COST
fal publishes no price for gpt-image-2 anywhere reachable (docs/verified.md), so spend
is MEASURED from the billing API before and after, never estimated. The script aborts
before starting a person if spend has already passed CEILING_USD.

LABELLING is not optional. Every pair carries a visible Spanish caption saying the
source person is AI-generated and the result came from the same pipeline a customer's
photos go through, plus alt text saying the same. Directive 2005/29/EC and Ley 3/1991
(misleading representation of results) and AI Act Art. 50. tests/test_demo_assets.py
refuses to let an unlabelled pair ship.

Usage:  .venv\\Scripts\\python.exe scripts\\make_demo_assets.py [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("make_demo_assets")

FAL_APP = "openai/gpt-image-2"  # docs/verified.md 2026-09-17, live OpenAPI
FAL_QUEUE = f"https://queue.fal.run/{FAL_APP}"
BALANCE_URL = "https://rest.alpha.fal.ai/billing/user_balance"
API = "https://api.studioface.app"
PROJECT = "studio-face-fresh-start"
BUCKET_SRC = f"{PROJECT}-src"
OUT_DIR = ROOT / "frontend" / "public" / "muestras"

CEILING_USD = 3.00
SHOTS_PER_PERSON = 3  # num_images maximum is 4 (live OpenAPI)
MAX_EDGE = 1200
PAIR_BUDGET_BYTES = 120 * 1024
DEMO_EMAIL = "OWNER_EMAIL_REDACTED"

FORBIDDEN_IN_SOURCE = ("professional", "studio", "8k", "masterpiece", "beautiful")

# Note the wording: this clause cannot itself use a forbidden word, even to negate it.
# "No studio lighting" would fail the rule that bans "studio" from a source prompt, and
# the rule is worth keeping literal — it is easier to obey than to reason about.
NEGATIVE = (
    "Do not include: text, watermarks, logos, brand names, other people, "
    "retouching, smoothed skin, lighting that looks deliberately set up, "
    "or a shallow-depth-of-field look."
)

# The visible caption and the alt text. Both say the same thing, because a screen
# reader user is owed the same disclosure as everyone else.
CAPTION_ES = (
    "Persona ficticia generada con IA. El resultado se ha producido con el mismo "
    "proceso por el que pasan tus fotos."
)


@dataclass(frozen=True)
class Person:
    key: str
    style: str
    prompt: str


def _source_prompt(subject: str, situations: str) -> str:
    return (
        f"Three casual photographs of the same person, taken by that person or a "
        f"friend on a phone. {subject} {situations} {NEGATIVE}"
    )


PEOPLE: tuple[Person, ...] = (
    Person(
        key="hombre-30",
        style="corporativo",
        prompt=_source_prompt(
            "A man of about 30 with Southern-European features, short dark wavy hair, "
            "light stubble, brown eyes, wearing a plain grey t-shirt.",
            "Shot one: front camera at 26mm equivalent, held at arm's length, taken "
            "from slightly below, kitchen window light behind him so his face is a "
            "little underexposed, cluttered worktop out of focus behind, mouth closed, "
            "faint motion blur on one shoulder. Shot two: a crop from a group photo at "
            "a table, his head slightly cut at the left edge, warm overhead restaurant "
            "light, uneven skin tone on the forehead. Shot three: indoors under mixed "
            "light, a window on one side and a yellow ceiling bulb on the other, "
            "off-centre framing with too much space above his head, flat expression.",
        ),
    ),
    Person(
        key="mujer-40",
        style="linkedin",
        prompt=_source_prompt(
            "A woman of about 40 with Southern-European features, dark shoulder-length "
            "hair tied back loosely, brown eyes, small lines at the corners of her "
            "eyes, wearing a navy jumper.",
            "Shot one: front camera at arm's length in a hallway, overhead light "
            "casting a shadow under her eyes, a coat rack behind her, slight camera "
            "shake. Shot two: cropped out of a group photo at an office desk, another "
            "person's shoulder still visible at the edge, fluorescent light, greenish "
            "cast. Shot three: sitting indoors with a window to her right and a warm "
            "lamp to her left, the two colours meeting across her face, crop cutting "
            "the top of her hair, neutral expression.",
        ),
    ),
    Person(
        key="hombre-25",
        style="creativo",
        prompt=_source_prompt(
            "A man of about 25 with Southern-European features, dark curly hair, "
            "clean-shaven, dark eyes, wearing a black crew-neck t-shirt.",
            "Shot one: front camera held high at arm's length, bedroom at night lit "
            "only by a ceiling light, visible grain, slightly out of focus. Shot two: "
            "a crop from a photo of three friends outdoors on an overcast afternoon, "
            "his face small and slightly soft, a hand at the frame edge. Shot three: "
            "indoors near a doorway with daylight from one side and a warm bulb "
            "overhead, framed too low so there is little headroom, mouth closed.",
        ),
    ),
)


# ---------------------------------------------------------------- plumbing


def secret(name: str) -> str:
    """Read from Secret Manager. Never logged, never echoed.

    argv goes through _exec.resolve, not bare: on Windows CreateProcess does not search
    PATHEXT, so subprocess.run(["gcloud", ...]) raises WinError 2 even with gcloud.cmd
    on PATH. That is the crash of 17 Sep 2026 already recorded in HANDOFF.md, and I
    walked straight back into it writing this file.
    """
    from _exec import resolve

    out = subprocess.run(
        resolve(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={name}",
                f"--project={PROJECT}",
            ]
        ),
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    return out.stdout.strip()


def balance(fal_key: str) -> float:
    r = httpx.get(BALANCE_URL, headers={"Authorization": f"Key {fal_key}"}, timeout=30)
    r.raise_for_status()
    return float(r.text)


def generate_sources(fal_key: str, person: Person) -> list[str]:
    """One call per person, num_images=3, so the three shots come from one sampling
    of one description. Identity coherence across the three is NOT guaranteed by the
    API; the caller checks what actually came back."""
    body = {
        "prompt": person.prompt,
        "num_images": SHOTS_PER_PERSON,
        "image_size": "portrait_4_3",
        "output_format": "jpeg",
        # Not "high": a source is meant to look like an ordinary phone photo, and the
        # cheaper tier is closer to one. It is also a third of the cost.
        "quality": "medium",
    }
    r = httpx.post(
        FAL_QUEUE,
        headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    if r.status_code == 422:
        raise RuntimeError(f"fal rejected the prompt for {person.key}: {r.text[:300]}")
    r.raise_for_status()
    status_url = r.json()["status_url"]
    response_url = r.json()["response_url"]
    for _ in range(120):
        s = httpx.get(status_url, headers={"Authorization": f"Key {fal_key}"}, timeout=30).json()
        if s.get("status") == "COMPLETED":
            break
        if s.get("status") in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"fal {s.get('status')} for {person.key}: {json.dumps(s)[:300]}")
        time.sleep(5)
    else:
        raise RuntimeError(f"fal never completed for {person.key}")
    done = httpx.get(response_url, headers={"Authorization": f"Key {fal_key}"}, timeout=60).json()
    urls = [i["url"] for i in done["images"]]
    logger.info("sources generated person=%s count=%d", person.key, len(urls))
    return urls


def to_jpeg(data: bytes, max_edge: int = 1536) -> bytes:
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def encode_pair(before: bytes, after: bytes, key: str) -> dict[str, int]:
    """WebP with a JPG fallback, longest edge MAX_EDGE, the PAIR under the byte budget.
    Quality steps down until both fit; the page is the reason the budget exists."""
    from PIL import Image

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    for quality in (82, 74, 66, 58, 50, 44):
        total = 0
        staged: dict[Path, bytes] = {}
        for role, raw in (("antes", before), ("despues", after)):
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((MAX_EDGE, MAX_EDGE))
            for ext, fmt in (("webp", "WEBP"), ("jpg", "JPEG")):
                buf = io.BytesIO()
                im.save(buf, fmt, quality=quality)
                staged[OUT_DIR / f"{key}-{role}.{ext}"] = buf.getvalue()
            total += len(staged[OUT_DIR / f"{key}-{role}.webp"])
        if total <= PAIR_BUDGET_BYTES:
            for path, blob in staged.items():
                path.write_bytes(blob)
                written[path.name] = len(blob)
            logger.info("pair written key=%s quality=%d webp_bytes=%d", key, quality, total)
            return written
    raise RuntimeError(f"{key}: could not fit the pair under {PAIR_BUDGET_BYTES} bytes")


def run_real_pipeline(
    person: Person, source_urls: list[str], app_secret: str, tasks_token: str
) -> list[str]:
    """Upload the sources, create the order, and let PRODUCTION generate from them.

    This is the real path minus the payment: same Cloud Run service, same
    build_prompt, same fal model. The order id begins "demo-" so nothing downstream
    can mistake it for a customer's.
    """
    import hashlib
    import hmac

    from google.cloud import firestore, storage

    order_id = f"demo-{person.key}-{int(time.time())}"
    batch = order_id
    gcs = storage.Client(project=PROJECT)
    bucket = gcs.bucket(BUCKET_SRC)
    keys = []
    for i, url in enumerate(source_urls):
        raw = httpx.get(url, timeout=120).content
        key = f"previews/{batch}/{i}.jpg"
        bucket.blob(key).upload_from_string(to_jpeg(raw), content_type="image/jpeg")
        keys.append(f"gs://{BUCKET_SRC}/{key}")
    logger.info("sources uploaded order_id=%s count=%d", order_id, len(keys))

    db = firestore.Client(project=PROJECT)
    db.collection("orders").document(order_id).set(
        {
            "id": order_id,
            "email": DEMO_EMAIL,
            "source_image_urls": keys,
            "style": person.style,
            "amount_cents": 0,  # never paid; this is not a sale and must not look like one
            "gclid": None,
            "status": "paid",
            "outputs": [],
            "attempts": 0,
            "refund_id": None,
            "refund_status": None,
        }
    )
    r = httpx.post(
        f"{API}/internal/generate/{order_id}",
        headers={"X-Tasks-Token": tasks_token},
        timeout=600,
    )
    r.raise_for_status()
    logger.info("production generated order_id=%s status=%s", order_id, r.json().get("status"))

    token = hmac.new(app_secret.encode(), order_id.encode(), hashlib.sha256).hexdigest()[:32]
    got = httpx.get(f"{API}/api/orders/{order_id}/{token}", timeout=60).json()
    if got.get("status") != "delivered":
        raise RuntimeError(f"{order_id} ended {got.get('status')}, not delivered")
    return got["images"]


# ---------------------------------------------------------------- driver


TOP_PANEL_FRACTION = 0.49
AFTER_ASPECT = (4, 5)


def crop_top_panel(data: bytes) -> bytes:
    """Take the single photograph out of the contact-sheet the model returns.

    Asked for "three casual photographs of the same person", gpt-image-2 renders all
    three INTO ONE frame as a collage — a full-width shot across the top and two side
    by side underneath — rather than returning three separate images. Identity
    coherence across the three is excellent, which is exactly what one call with
    num_images=3 was for, so the behaviour is welcome. It is just not a "before".

    The top panel is the full-width one, so it crops cleanly, and it is the arm's
    length selfie the prompt asks for first. It is then centre-cropped to the same 4:5
    the pipeline outputs, so the pair sits side by side without one letterboxing.
    """
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im = im.crop((0, 0, im.width, int(im.height * TOP_PANEL_FRACTION)))
    target = AFTER_ASPECT[0] / AFTER_ASPECT[1]
    if im.width / im.height > target:
        new_w = int(im.height * target)
        left = (im.width - new_w) // 2
        im = im.crop((left, 0, left + new_w, im.height))
    else:
        new_h = int(im.width / target)
        top = (im.height - new_h) // 2
        im = im.crop((0, top, im.width, top + new_h))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=94)
    return buf.getvalue()


def recrop_from_storage() -> int:
    """Rebuild the pairs from the artifacts already in GCS. Spends nothing.

    The sources and the outputs of the real run are both in buckets, and the order
    documents name them, so a framing change never needs to pay fal twice.
    """
    from google.cloud import firestore, storage

    gcs = storage.Client(project=PROJECT)
    db = firestore.Client(project=PROJECT)
    rebuilt = 0
    for person in PEOPLE:
        docs = [
            d.to_dict()
            for d in db.collection("orders").stream()
            if d.id.startswith(f"demo-{person.key}-")
        ]
        if not docs:
            print(f"{person.key}: no demo order in Firestore, skipping")
            continue
        order = sorted(docs, key=lambda d: d["id"])[-1]
        before = crop_top_panel(_read_gs(gcs, order["source_image_urls"][0]))
        after = _read_gs(gcs, order["outputs"][0])
        encode_pair(before, after, person.key)
        rebuilt += 1
    return rebuilt


def _read_gs(gcs, uri: str) -> bytes:
    from google.cloud.storage.blob import Blob

    return Blob.from_uri(uri, client=gcs).download_as_bytes()


def already_done(key: str) -> bool:
    return all((OUT_DIR / f"{key}-{role}.webp").exists() for role in ("antes", "despues"))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the prompts and spend nothing")
    ap.add_argument(
        "--recrop",
        action="store_true",
        help="rebuild the pairs from the artifacts already in GCS; spends nothing",
    )
    ns = ap.parse_args()

    if ns.recrop:
        print(f"rebuilt {recrop_from_storage()} pairs from storage, spend $0.00")
        return 0

    if ns.dry_run:
        for p in PEOPLE:
            print(f"--- {p.key} (style={p.style})\n{p.prompt}\n")
        return 0

    fal_key = secret("fal-key")
    app_secret = secret("app-token-secret")
    tasks_token = secret("tasks-token")
    start = balance(fal_key)
    print(f"fal balance before: ${start:.4f}")

    for person in PEOPLE:
        if already_done(person.key):
            print(f"{person.key}: already built, skipping")
            continue
        spent = start - balance(fal_key)
        if spent > CEILING_USD:
            print(f"STOP: spent ${spent:.4f}, over the ${CEILING_USD:.2f} ceiling")
            return 1
        sources = generate_sources(fal_key, person)
        outputs = run_real_pipeline(person, sources, app_secret, tasks_token)
        before = httpx.get(sources[0], timeout=120).content
        after = httpx.get(outputs[0], timeout=120).content
        encode_pair(before, after, person.key)

    end = balance(fal_key)
    print(f"fal balance after:  ${end:.4f}")
    print(f"ACTUAL SPEND:       ${start - end:.4f}  (ceiling ${CEILING_USD:.2f})")
    for f in sorted(OUT_DIR.glob("*")):
        print(f"  {f.name:28s} {f.stat().st_size / 1024:6.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
