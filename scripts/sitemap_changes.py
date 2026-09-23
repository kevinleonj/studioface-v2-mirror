"""Which sitemap URLs changed between two sitemaps: new, or with a different <lastmod>.

Task 95b. The deploy saves the live /sitemap.xml before it deploys, fetches the new one
after verify_production.py passes, and submits only these URLs to IndexNow. Resubmitting
unchanged URLs on every deploy is what task 95a's content dates exist to prevent.

An unreadable or missing OLD sitemap (a first deploy, a failed fetch) means every URL in
the new one counts as changed. An unreadable NEW sitemap is an error: submitting from a
guess is worse than submitting nothing. Usage:
    python scripts/sitemap_changes.py OLD.xml NEW.xml   # one URL per line on stdout
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _lastmods(xml_text: str) -> dict[str, str]:
    """url -> lastmod, in document order. Raises ValueError when it is not a sitemap."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"not XML: {exc}") from exc
    if root.tag != f"{{{NS['s']}}}urlset":
        raise ValueError(f"not a sitemap urlset: {root.tag}")
    return {
        (u.findtext("s:loc", namespaces=NS) or "").strip(): (
            u.findtext("s:lastmod", namespaces=NS) or ""
        ).strip()
        for u in root.findall("s:url", NS)
    }


def changed_urls(old_xml: str | None, new_xml: str) -> list[str]:
    new = _lastmods(new_xml)
    try:
        old = _lastmods(old_xml) if old_xml else {}
    except ValueError:
        old = {}
    return [url for url, lastmod in new.items() if url and old.get(url) != lastmod]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: sitemap_changes.py OLD.xml NEW.xml", file=sys.stderr)
        return 2
    old_path, new_path = Path(argv[1]), Path(argv[2])
    old = old_path.read_text(encoding="utf-8") if old_path.is_file() else None
    try:
        urls = changed_urls(old, new_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"new sitemap unreadable: {exc}", file=sys.stderr)
        return 2
    # Nothing at all when nothing changed: the deploy step tests the file for emptiness.
    if urls:
        print("\n".join(urls))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
