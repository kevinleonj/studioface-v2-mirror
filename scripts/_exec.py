"""One rule for launching CLIs from Python on every OS.

Windows: CreateProcess does not search PATHEXT, so `subprocess.run(["gcloud", ...])` raises
WinError 2 even though `gcloud.cmd` is on PATH (the exact crash of 17 Sep 2026). shutil.which()
does search PATHEXT, so every argv[0] goes through it before Popen. No shell=True anywhere.
"""

from __future__ import annotations

import shutil


def resolve(args: list[str]) -> list[str]:
    exe = shutil.which(args[0])
    if exe is None:
        raise FileNotFoundError(f"'{args[0]}' is not on PATH in this terminal")
    return [exe, *args[1:]]
