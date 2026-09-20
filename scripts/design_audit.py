"""Deterministic AI-slop detector for a built frontend.

Why it exists: Playwright assertions and Lighthouse scores pass on ugly pages. This
script does not judge beauty either — it detects the *defaults*, the choices a model
reaches for when nobody decided.
Sources for the catalogue (accessed 17 Sep 2026): vibecodekit.dev/ai-slop-design,
925studios.co/blog/ai-slop-web-design-guide, claudecodehq.com/playbooks/unslop-ui (3.2M-post Reddit
analysis; note its finding that the 2026 tell is the "tasteful default": cream + serif + sage),
sailop.com/blog/ai-slop-2026-state-of-the-ai-generated-web, funboy322/avoid-ai-design.

Usage:  python scripts/design_audit.py frontend/out [--json out.json]
Exit 1 on any P0 or more than two P1 findings. It is a floor, not a judge: the vision critique in
docs/design-review/ is what decides whether the page is good.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SLOP_FONTS = ("inter", "poppins", "geist", "roboto", "arial", "space grotesk")
TASTEFUL_SERIFS = ("instrument serif", "playfair", "fraunces", "dm serif", "libre baskerville")
AI_PURPLE = re.compile(
    r"(violet|indigo|purple)-(4|5|6|7)00|#(7c3aed|6366f1|8b5cf6|a855f7|4f46e5)", re.IGNORECASE
)
SAGE = re.compile(r"#(8a9a5b|9caf88|a3b18a|87a96b|b2ac88)|sage|olive-?green", re.IGNORECASE)
CREAM = re.compile(r"#(faf9f6|fdfbf7|fffdf8|f5f0e8|faf8f5|fefae0|fafaf7)", re.IGNORECASE)
GRADIENT_BG = re.compile(r"bg-gradient-to-|linear-gradient\(", re.IGNORECASE)
GRADIENT_TEXT = re.compile(
    r"bg-clip-text|text-transparent|-webkit-background-clip:\s*text", re.IGNORECASE
)
SHADCN_CARD = re.compile(r"rounded-2xl[^\"']*shadow-lg|shadow-lg[^\"']*rounded-2xl", re.IGNORECASE)
LEFT_STRIP = re.compile(r"border-l-[34]\b|border-left:\s*[34]px", re.IGNORECASE)
ICON_SQUARE = re.compile(
    r"(rounded-(lg|xl|2xl))[^\"']*\b(bg-\w+-(50|100|200))\b[^\"']*\b(p-[23])\b", re.IGNORECASE
)
DEFAULT_BLUE = re.compile(r"bg-blue-600|#2563eb", re.IGNORECASE)
EMOJI = re.compile("[\U0001f300-\U0001faff\u2700-\u27bf\u2600-\u26ff]")
SLOP_COPY = re.compile(
    r"eleva tu|elevate your|all-in-one|sin l[ií]mites|the future of", re.IGNORECASE
)
# Anthropic's own frontend-design skill lists these as the current generated-page clusters.
# They are NOT covered by the external slop catalogues, which is how a page can clear this
# script and still be a default: cluster 3 (broadsheet) and the cluster-5 chrome.
# Order-independent on purpose. The first version required text-transform BEFORE
# letter-spacing, and Tailwind compiled our own .sf-label the other way round, so 51
# uses of a tracked uppercase mono label sailed through the rule written to catch them.
# A detector that depends on the order a compiler happens to emit is not a detector.
UPPER_TRACKED = re.compile(
    r"(uppercase[^\"']*tracking-\[?0?\.[12]|tracking-\[?0?\.[12][^\"']*uppercase"
    r"|text-transform:\s*uppercase[^}]*letter-spacing:\s*0?\.[12]"
    r"|letter-spacing:\s*0?\.[12][^}]*text-transform:\s*uppercase)",
    re.IGNORECASE,
)
MONO_LABEL = re.compile(
    r"font-(mono|chivo|ibm-plex-mono|jetbrains)|--font-[\w-]*mono", re.IGNORECASE
)
HAIRLINE = re.compile(
    r"border(-[trbl])?-\[?1px\]?|border(-[trbl])?(-width)?:\s*1px|\bborder-b-\[3px\]", re.IGNORECASE
)
ZERO_RADIUS = re.compile(r"--radius:\s*0(px|rem)?\b|rounded-none", re.IGNORECASE)
HEADLINE_ACCENT = re.compile(
    r"<h1[^>]*>(?:(?!</h1>).){0,400}?<(span|em|strong|b)[^>]*(class|style)=\"[^\"]*"
    r"(text-\[|color:|border-b|underline|font-bold|italic)",
    re.IGNORECASE | re.DOTALL,
)
ARROW_LINK = re.compile(r">[^<]{2,40}(→|-&gt;|&rarr;)\s*<", re.IGNORECASE)
MIDDOT_META = re.compile(r"[^\s>]\s·\s[^\s<]{1,30}\s·\s", re.IGNORECASE)
TINTED_BLACK = re.compile(r"#(0b0b0b|111111|0a0a0a|121212)\b", re.IGNORECASE)
FONT_FAMILY = re.compile(r"font-family:\s*([^;}]+)", re.IGNORECASE)  # quotes kept, stripped below
FONT_SIZE = re.compile(r"font-size:\s*([\d.]+(?:rem|px|em))", re.IGNORECASE)
HEX = re.compile(r"#[0-9a-f]{6}\b", re.IGNORECASE)


@dataclass
class Finding:
    severity: str
    rule: str
    evidence: str
    where: str


def _hits(pattern: re.Pattern, text: str) -> list[tuple[int, str]]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = pattern.search(line)
        if m:
            out.append((i, line.strip()[:120]))
    return out


def typography_findings(text: str, name: str) -> list[Finding]:
    """The two typography judgements. Split out to keep audit_text under the project's
    complexity ceiling of 8; everything else in the catalogue is a plain regex."""
    families = {
        m.strip().lower().replace('"', "").replace("'", "") for m in FONT_FAMILY.findall(text)
    }
    joined = " ".join(families)
    distinctive = [
        x for x in families if not any(s in x for s in SLOP_FONTS) and x.strip() != "sans-serif"
    ]
    out: list[Finding] = []
    if any(s in joined for s in SLOP_FONTS) and not distinctive:
        out.append(Finding("P0", "only-default-typeface", joined[:120] or "(none)", name))
    if any(s in joined for s in TASTEFUL_SERIFS) and (CREAM.search(text) or SAGE.search(text)):
        out.append(Finding("P0", "tasteful-default-2026 (cream+serif+sage)", joined[:120], name))
    return out


def skill_findings(text: str, name: str, add) -> list[Finding]:
    """Anthropic frontend-design skill calibration, clusters 3 and 5.

    These are NOT in the external slop catalogues, which is how a page clears this
    script and is still a default: our own direction B is cluster 3, and .sf-label is
    cluster 5 fifty-one times over.
    """
    out: list[Finding] = []
    eyebrows = UPPER_TRACKED.findall(text)  # count every use, not one per line
    if len(eyebrows) > 2:
        out.append(
            Finding(
                "P0", "allcaps-tracked-eyebrow (skill cluster 5)", f"{len(eyebrows)} uses", name
            )
        )
    if HAIRLINE.search(text) and ZERO_RADIUS.search(text) and MONO_LABEL.search(text):
        out.append(
            Finding(
                "P0",
                "broadsheet-default (hairlines + zero radius + mono labels, skill cluster 3)",
                "1px rules + --radius:0 + a mono family in one sheet",
                name,
            )
        )
    add("P1", "headline-single-phrase-accent (skill)", HEADLINE_ACCENT)
    add("P1", "arrow-in-link-text (skill cluster 5)", ARROW_LINK)
    add("P1", "middot-meta-string (skill cluster 5)", MIDDOT_META)
    add("P1", "tinted-near-black (skill cluster 5)", TINTED_BLACK)
    return out


def audit_text(text: str, name: str) -> list[Finding]:
    f: list[Finding] = []

    def add(sev: str, rule: str, pattern: re.Pattern) -> list[tuple[int, str]]:
        hits = _hits(pattern, text)
        if hits:
            f.append(Finding(sev, rule, hits[0][1], f"{name}:{hits[0][0]}"))
        return hits

    f += typography_findings(text, name)
    add("P0", "ai-purple-primary", AI_PURPLE)
    add("P0", "gradient-text", GRADIENT_TEXT)
    grad = add("P1", "gradient-background", GRADIENT_BG)
    if len(grad) > 2:
        f.append(Finding("P0", "gradients-everywhere", f"{len(grad)} gradient declarations", name))
    cards = add("P1", "untouched-shadcn-card (rounded-2xl + shadow-lg)", SHADCN_CARD)
    if len(cards) > 2:
        f.append(Finding("P0", "cardocalypse", f"{len(cards)} default cards", name))
    add("P1", "left-border-strip", LEFT_STRIP)
    add("P1", "icon-in-rounded-square", ICON_SQUARE)
    add("P1", "default-blue-button", DEFAULT_BLUE)
    add("P1", "emoji-in-ui", EMOJI)
    add("P1", "averaged-copy", SLOP_COPY)

    f += skill_findings(text, name, add)

    sizes = {s.lower() for s in FONT_SIZE.findall(text)}
    if len(sizes) > 12:
        f.append(Finding("P2", "no-type-scale", f"{len(sizes)} distinct font sizes", name))
    colors = {c.lower() for c in HEX.findall(text)}
    if colors and colors <= {"#ffffff", "#000000", "#fff", "#000"}:
        f.append(Finding("P2", "black-and-white-only", ", ".join(sorted(colors)), name))
    return f


TRACKED_CLASS = re.compile(r"\.([\w-]+)\s*\{[^}]*\}")


def eyebrow_usage(root: Path) -> list[Finding]:
    """Count how often a tracked-uppercase class is USED, not how often it is declared.

    The per-file rule counts declarations, and a utility class is declared once. Our own
    .sf-label is one CSS rule and fifty-one usages across the built HTML — the cluster-5
    device on every page, invisible to a counter that stops at the stylesheet.
    """
    classes: set[str] = set()
    for css in root.rglob("*.css"):
        text = css.read_text(encoding="utf-8", errors="ignore")
        for match in TRACKED_CLASS.finditer(text):
            if UPPER_TRACKED.search(match.group(0)):
                classes.add(match.group(1))
    if not classes:
        return []
    uses = 0
    for html in root.rglob("*.html"):
        body = html.read_text(encoding="utf-8", errors="ignore")
        uses += sum(body.count(name) for name in classes)
    if uses <= 2:
        return []
    named = ", ".join(sorted(classes))
    return [
        Finding(
            "P0",
            "allcaps-tracked-eyebrow (skill cluster 5)",
            f"{uses} uses of {named}",
            "across the export",
        )
    ]


def audit_dir(root: Path) -> list[Finding]:
    files = [p for p in root.rglob("*") if p.suffix.lower() in {".html", ".css"} and p.is_file()]
    if not files:
        raise SystemExit(f"no .html/.css under {root} — build the frontend first")
    out: list[Finding] = []
    for p in files:
        out += audit_text(p.read_text(encoding="utf-8", errors="ignore"), str(p.relative_to(root)))
    out += eyebrow_usage(root)
    return out


def main() -> None:
    # This detector's own catalogue includes emoji-in-ui, so an evidence line can carry
    # the emoji it just caught. On a cp1252 console — the Windows default, and what the
    # gate gets when launched from a hook — printing that raises UnicodeEncodeError
    # MID-REPORT, after the exit code is already 1. The run then looks like a
    # legitimate FAIL while every finding after the emoji one silently vanishes:
    # `5 P0, 7 P1` collapses to one visible line.
    #
    # This is the second time: fixed on 17 Sep, lost when the file was rewritten, and
    # it came back the moment the Stop hook ran the gate in a cp1252 shell rather than
    # my UTF-8 one. errors="replace" keeps the console's real encoding and degrades the
    # one unprintable character instead of losing the rest of the report.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ns = ap.parse_args()
    findings = audit_dir(Path(ns.root))
    order = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda x: (order[x.severity], x.rule))
    for x in findings:
        print(f"{x.severity}  {x.rule:46s} {x.where:28s} {x.evidence}")
    p0 = sum(1 for x in findings if x.severity == "P0")
    p1 = sum(1 for x in findings if x.severity == "P1")
    print(f"\nDESIGN AUDIT: {p0} P0, {p1} P1, {len(findings) - p0 - p1} P2")
    if ns.json:
        Path(ns.json).write_text(
            json.dumps([asdict(x) for x in findings], indent=2), encoding="utf-8"
        )
    if p0 or p1 > 2:
        print("FAIL: a P0 tell, or more than two P1 tells, means the design was not decided.")
        sys.exit(1)
    print("PASS (floor only: the vision critique decides whether it is good)")


if __name__ == "__main__":
    main()
