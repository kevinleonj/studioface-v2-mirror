"""Guards: rate limiting for the free preview, upload validation, prompt building.

All three are pure functions over injected state so they run in tests without
Firestore. In production the RateLimiter's `store` is a Firestore collection
and `now` is time.time; here they are a dict and a fake clock.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

# ---------------------------------------------------------------- rate limiting


class Counter(Protocol):
    """Atomic counter shared by ALL Cloud Run instances. Production adapter:
    Firestore transaction (adapters/firestore_counter.py). Test adapter:
    MemoryCounter below. Never a per-process dict: many instances, one count."""

    def increment_if_below(self, key: str, limit: int, ttl_s: int) -> bool: ...

    def decrement(self, key: str) -> None: ...


@dataclass
class MemoryCounter:
    now: Callable[[], float] = time.time
    store: dict = field(default_factory=dict)

    def increment_if_below(self, key: str, limit: int, ttl_s: int) -> bool:
        t = self.now()
        n, exp = self.store.get(key, (0, t + ttl_s))
        if t >= exp:
            n, exp = 0, t + ttl_s
        if n >= limit:
            self.store[key] = (n, exp)
            return False
        self.store[key] = (n + 1, exp)
        return True

    def decrement(self, key: str) -> None:
        """Give back one try. A rolled-over window or a count already at 0 is left
        alone, so this can never resurrect a stale document or underflow."""
        if key not in self.store:
            return
        t = self.now()
        n, exp = self.store[key]
        if t >= exp or n <= 0:
            return
        self.store[key] = (n - 1, exp)


@dataclass
class RateLimiter:
    """Three ceilings, all server-side, all in the shared counter:
    - per client: `per_client` previews per `window_s` (salted hash of IP + UA, no raw IP)
    - per /24 subnet: `per_subnet` per `window_s`, so rotating IPs in one block still hit a wall
    - global per UTC day: `daily_global`, which bounds the fal bill regardless of what a bot does
    Narrow ceilings are checked first so a rejected client never consumes global budget.
    """

    counter: Counter
    per_client: int = 3
    per_subnet: int = 20
    window_s: int = 3600
    daily_global: int = 300
    # Task 29: storing photos without generating is cheap but not free, so the
    # fallback that keeps the buy button alive once `per_client` is spent still has a
    # ceiling of its own — ten stored batches per visitor per hour, then the real 429.
    per_store: int = 10
    salt: str = "change-me"
    now: Callable[[], float] = time.time

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join((self.salt, *parts)).encode()).hexdigest()[:24]

    def check_named(self, action: str, ip: str, limit: int, window_s: int) -> bool:
        """A ceiling for something other than the preview, under its own key, so the
        two budgets cannot eat each other."""
        return self.counter.increment_if_below(f"{action}:{self._hash(ip)}", limit, window_s)

    def check_store(self, ip: str, user_agent: str) -> bool:
        """Task 29's own ceiling, in its own namespace (`store:`) so it can never eat
        the preview budget's keys or be eaten by them. Same client identity as
        `check` (ip+user_agent hash) — a visitor's storage budget is the same visitor
        whether or not the model ever ran for them."""
        key = f"store:{self._hash(ip, user_agent)}"
        return self.counter.increment_if_below(key, self.per_store, self.window_s)

    def _keys(self, ip: str, user_agent: str) -> tuple[str, str, str]:
        """The three keys one preview touches. `check` and `refund` both call this,
        so the two can never drift apart and give back the wrong document."""
        day = str(int(self.now() // 86400))
        subnet = ".".join(ip.split(".")[:3]) if ip.count(".") == 3 else ip
        return f"c:{self._hash(ip, user_agent)}", f"s:{self._hash(subnet)}", f"g:{day}"

    def check(self, ip: str, user_agent: str) -> tuple[bool, str]:
        client_key, subnet_key, daily_key = self._keys(ip, user_agent)
        # Narrow ceilings first, so a rejected client never consumes global budget.
        if not self.counter.increment_if_below(client_key, self.per_client, self.window_s):
            return False, "client_cap"
        if not self.counter.increment_if_below(subnet_key, self.per_subnet, self.window_s):
            return False, "subnet_cap"
        if not self.counter.increment_if_below(daily_key, self.daily_global, 86400):
            return False, "daily_cap"
        return True, "ok"

    def refund(self, ip: str, user_agent: str) -> None:
        """Give back the try `check` just granted, because the model refused or
        failed. Task 28: count BEFORE the model call, refund after a failure — chosen
        over counting only after success, which needs a non-atomic peek and reopens
        the race two requests both seeing "2 used" and both proceeding at real fal
        cost. Traded away: a process dying between `check` and this call keeps the
        try spent. HANDOFF.md, task 28, has the full reasoning.
        """
        for key in self._keys(ip, user_agent):
            self.counter.decrement(key)


# ---------------------------------------------------------------- upload validation

MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # RIFF....WEBP, checked below
}
MAX_FILES, MIN_FILES = 4, 1
MAX_BYTES = 12 * 1024 * 1024


def sniff(data: bytes) -> str | None:
    """Detect type from bytes, never from the filename or the client's header."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypheif"):
        return "image/heic"
    return None


@dataclass
class ValidatedUpload:
    accepted: list[tuple[str, bytes]]  # (mime, bytes) in original order
    needs_heic_conversion: list[int]  # indices to convert before fal


def validate_uploads(files: list[bytes]) -> ValidatedUpload:
    if not (MIN_FILES <= len(files) <= MAX_FILES):
        raise ValueError(f"upload_count:{len(files)}")
    accepted, heic = [], []
    for i, data in enumerate(files):
        if len(data) > MAX_BYTES:
            raise ValueError(f"file_too_large:{i}")
        mime = sniff(data)
        if mime is None:
            raise ValueError(f"unsupported_type:{i}")
        if mime == "image/heic":
            heic.append(i)
        accepted.append((mime, data))
    return ValidatedUpload(accepted=accepted, needs_heic_conversion=heic)


# ---------------------------------------------------------------- prompts

# Structure follows Google's own photorealistic template, quoted in docs/verified.md:
# "A photorealistic [type of shot] of a [subject description] in a [setting
# description]. [Description of the light]. Shot from a [camera angle] with a [lens
# type]." Google also asks for full prose rather than comma-separated keywords.
#
# The identity clause is repeated at both ends. The old comment here claimed the model
# "weights the edges of the instruction"; that is folklore and the research could not
# find a source for it either way, so it stays for now as a cheap redundancy rather
# than as a claim. The part that IS sourced is the phrasing: Google's documented
# preservation pattern is an instruction to keep features unchanged, not a list of
# things not to do.
IDENTITY = (
    "The person in the reference photos. Keep the exact same face, facial structure, "
    "skin tone, eye colour, hair colour, hairstyle, face shape and apparent age, "
    "including their natural asymmetry and existing skin texture."
)

STYLES = {
    "corporativo": dict(
        env="a neutral mid-grey seamless studio backdrop",
        light="soft, even key light from front-left with a gentle fill that keeps the shadows open",
        wardrobe="a dark navy blazer over a plain white shirt",
        mood="composed and confident, closed-mouth smile",
    ),
    "linkedin": dict(
        env="a bright modern office blurred far behind",
        light="natural window light from the side",
        wardrobe="a smart-casual light blue shirt with an open collar",
        mood="warm and approachable, slight natural smile",
    ),
    "creativo": dict(
        env="a textured warm-beige wall",
        light="soft directional daylight",
        wardrobe="a plain black crew-neck top",
        mood="relaxed and direct gaze",
    ),
}

# The customer chooses the GARMENT, never their gender.
#
# STYLES above each carried one hard-coded wardrobe and all three were menswear, so
# every customer got a man's shirt whoever they were. The obvious repair is a gender
# question; this is deliberately not one. Asking about the person collects an identity
# attribute in order to sell a photograph — GDPR Art. 9 does not name gender identity
# among the special categories, but "probably ordinary personal data" is not a position
# worth defending when the alternative costs nothing, and Spain's Ley 4/2023 makes
# self-declared sex legally authoritative anyway. Asking about the OUTPUT collects
# nothing, and serves more people: anyone can want the tailored jacket, anyone can want
# the blouse. Aragon.ai, the one competitor in this category we could verify, sells
# "choice of attire" and never asks either.
#
# Labels are what a customer reads in the picker, so they name clothes. No option is
# named after a kind of person, and tests/test_wardrobe.py holds that line.
WARDROBES: dict[str, dict[str, str]] = {
    "blazer-camisa": {
        "label": "Blazer y camisa blanca",
        "prompt": "a dark navy blazer over a plain white shirt",
    },
    "blusa-sastre": {
        "label": "Chaqueta sastre y blusa",
        "prompt": "a tailored dark navy jacket over a plain white blouse",
    },
    "camisa-azul": {
        "label": "Camisa azul, sin corbata",
        "prompt": "a smart-casual light blue shirt with an open collar",
    },
    "blusa-clara": {
        "label": "Blusa azul claro",
        "prompt": "a smart-casual light blue blouse",
    },
    "jersey-cuello-alto": {
        "label": "Jersey de cuello alto",
        "prompt": "a fine-knit charcoal roll-neck jumper",
    },
    "negro-basico": {
        "label": "Camiseta negra lisa",
        "prompt": "a plain black crew-neck top",
    },
}

# Affirmative on purpose. Google's image-generation guidance says to "use semantic
# negative prompts that describe the scene positively ('an empty street') rather than
# stating what not to include" (docs/verified.md, 2026-09-17), and nano-banana-2 is a
# Gemini-family model with no separate negative-conditioning input — so every noun in
# an exclusion list was simply more subject matter. The previous clause read "No text,
# no logo, no watermark, no hands, no extra people, no over-smoothed skin, no cartoon
# or painting effect", which is the textbook way to get hands in the frame.
#
# Each sentence below stands in for one of those prohibitions, and
# tests/test_prompt_phrasing.py fails if any of them is dropped or if an exclusion word
# ever reappears anywhere in a built prompt.
# Careful here: an affirmative clause can contradict the style it sits next to. The
# first draft said "against a clean plain backdrop", which fought "a bright modern
# office blurred far behind" in the linkedin style — two different settings in one
# prompt. It describes what is IN the frame instead, and leaves the setting to STYLES.
SCENE_FACTS = (
    "The person is alone in the frame, shown from the chest up, with their hands out of "
    "shot. Every surface behind them is plain and unmarked. The skin keeps its natural "
    "texture, with visible pores and fine lines. The result is a photograph."
)


def default_wardrobe_key(style: str) -> str | None:
    """Which WARDROBES key names the garment this style wears by default.

    Unit F6. The preview is made with `wardrobe=None`, which uses the style's own
    garment, and the page has to be able to NAME that to the customer. Derived by
    matching the prompt text rather than written down, so editing a style cannot leave
    the label behind saying something that is no longer true.
    """
    wanted = STYLES[style]["wardrobe"]
    return next((k for k, v in WARDROBES.items() if v["prompt"] == wanted), None)


def build_prompt(style: str, variant: int, wardrobe: str | None = None) -> str:
    """Style sets the scene, wardrobe sets the clothes.

    `wardrobe=None` keeps the style's original garment, so an order placed before the
    picker existed generates exactly what it would have generated before. An unknown
    key raises rather than falling back: a typo silently selling someone clothes they
    did not pick is a defect they would only discover after paying.
    """
    s = STYLES[style]
    clothing = WARDROBES[wardrobe]["prompt"] if wardrobe else s["wardrobe"]
    framing = [
        "head-and-shoulders portrait, subject centred",
        "head-and-shoulders portrait, subject slightly left of centre",
        "chest-up portrait, subject centred, three-quarter turn",
        "tight head-and-shoulders portrait, subject centred",
    ][variant % 4]
    return (
        f"A photorealistic {framing} of {IDENTITY} "
        f"The person is wearing {clothing}, expression {s['mood']}, "
        f"set in {s['env']}. The scene is illuminated by {s['light']}. "
        f"Captured with an 85mm portrait lens at f/2.8, shallow depth of field, "
        f"emphasising natural skin texture with visible pores, sharp focus on the eyes. "
        f"Vertical 4:5 format. {SCENE_FACTS} {IDENTITY}"
    )
