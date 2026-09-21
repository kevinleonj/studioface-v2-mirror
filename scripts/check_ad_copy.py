"""Validate docs/ads/rsa.json against Google Ads responsive search ad limits.

Limits verified 19 September 2026 at https://support.google.com/google-ads/answer/7684791:
headline 30 characters (up to 15), description 90 characters (up to 4), path 15 characters (2).

Task 24: rsa.json now holds two ad groups (cv, linkedin), each with its own headlines,
descriptions and path — so every group is validated independently, and "no duplicates"
means no duplicates INSIDE one group. The same headline reused across the two groups
(e.g. "Prueba gratis, sin registro") is not a violation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LIMITS = {"headlines": (30, 15), "descriptions": (90, 4), "path": (15, 2)}


def find_group_violations(name: str, group: dict) -> list[str]:
    violations: list[str] = []
    for field, (max_characters, max_items) in LIMITS.items():
        items = group.get(field, [])
        if len(items) > max_items:
            violations.append(f"{name}/{field}: {len(items)} items, limit {max_items}")
        if len(set(items)) != len(items):
            violations.append(f"{name}/{field}: duplicate entries")
        for text in items:
            if len(text) > max_characters:
                violations.append(f"{name}/{field}: {len(text)}/{max_characters} '{text}'")
    return violations


def find_violations(data: dict) -> list[str]:
    violations: list[str] = []
    for group in data.get("ad_groups", []):
        violations.extend(find_group_violations(group.get("name", "?"), group))
    return violations


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("docs/ads/rsa.json")
    violations = find_violations(json.loads(path.read_text(encoding="utf-8")))
    for line in violations:
        print(line)
    print("FAIL" if violations else "OK: all assets within limits")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
