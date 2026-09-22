"""Read or flip the shop's kill switch, from anywhere a phone can run this
(a Termux/SSH shell with gcloud installed, or Kevin's own machine).

Usage:
    python scripts/killswitch.py --status
    python scripts/killswitch.py --on
    python scripts/killswitch.py --off

Reads and writes the exact document the app's own order store reads --
config/killswitch, field "on" -- app/entry.py's FirestoreOrderStore.killswitch
property/setter (app/core.py's OrderStore.killswitch docstring: "Firestore doc
config/killswitch in prod"). This script calls FirestoreOrderStore itself rather
than writing a second path to the same document, so it can never drift from what
/api/checkout and /api/preview (app/main.py) actually check. The path is
operational information, already printed in docs/GO-LIVE.md -- not a secret.

Before touching production, gcloud is resolved with shutil.which (scripts/_exec.py,
the same fix scripts/set_secret.py uses for Windows' CreateProcess/PATHEXT gap) and
asked which project it is pointed at, so --on/--off can never hit the wrong Google
Cloud project by accident.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _exec import resolve  # noqa: E402

from app.entry import FirestoreOrderStore  # noqa: E402

PROJECT = "studio-face-fresh-start"
KILLSWITCH_DOC = "config/killswitch"


def read_status(store: FirestoreOrderStore) -> bool:
    """True: the shop is stopped. False: the shop is selling."""
    return store.killswitch


def turn_on(store: FirestoreOrderStore) -> None:
    """Stop the shop selling. Same transition app/core.py already uses for the
    fal-credit lockout and the daily order ceiling -- this just gives Kevin the
    same switch by hand."""
    store.killswitch = True


def turn_off(store: FirestoreOrderStore) -> None:
    """Let the shop sell again. There was no code path that did this before this
    script -- app/main.py's /internal/budget can only turn the switch ON."""
    store.killswitch = False


def _active_gcloud_project() -> str:
    """Raises FileNotFoundError if gcloud is not on PATH, and SystemExit if it is
    on PATH but pointed at a project other than PROJECT."""
    argv = resolve(["gcloud", "config", "get-value", "project"])
    result = subprocess.run(argv, capture_output=True, text=True, check=True)
    active = result.stdout.strip()
    if active != PROJECT:
        raise SystemExit(f"gcloud project is '{active}', expected '{PROJECT}' -- stopping")
    return active


def _real_store() -> FirestoreOrderStore:
    from google.cloud import firestore

    _active_gcloud_project()
    return FirestoreOrderStore(firestore.Client(project=PROJECT))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Read or flip the StudioFace kill switch.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="print whether the shop is stopped")
    group.add_argument("--on", action="store_true", help="stop the shop selling")
    group.add_argument("--off", action="store_true", help="let the shop sell again")
    args = parser.parse_args(argv[1:])

    print(f"document: {KILLSWITCH_DOC}")
    try:
        store = _real_store()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127

    if args.on:
        turn_on(store)
    elif args.off:
        turn_off(store)
    on = read_status(store)
    print(f"killswitch: {'ON (shop stopped)' if on else 'OFF (shop selling)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
