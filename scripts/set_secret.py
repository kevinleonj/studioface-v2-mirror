"""Add a Secret Manager version from a hidden prompt. Usage: python scripts/set_secret.py <name>

The value never appears on a screen, in a log, in shell history, or in an argv list:
it is piped to gcloud over stdin (--data-file=-), and only printed back to the caller
as a hidden getpass prompt while typing.

On Windows gcloud is gcloud.cmd. CreateProcess does not search PATHEXT, so
subprocess.run(["gcloud", ...]) used to raise WinError 2 even with gcloud on PATH
(the 17 Sep 2026 lesson). argv[0] goes through _exec.resolve, which uses
shutil.which, the same fix bootstrap.py already uses.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _exec import resolve  # noqa: E402


def add_secret_version(name: str, value: str) -> None:
    """Pipe value to gcloud on stdin. value is never an argv token, never printed."""
    subprocess.run(
        resolve(["gcloud", "secrets", "versions", "add", name, "--data-file=-"]),
        input=value,
        text=True,
        check=True,
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: set_secret.py <name>", file=sys.stderr)
        return 2
    name = argv[1]
    value = getpass.getpass(f"{name}: ")
    try:
        add_secret_version(name, value)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    print(f"{name}: version added")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
