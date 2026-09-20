"""Read a DMARC aggregate report and say, in one line, whether anything failed.

These arrive daily and forever, as a zip of XML, and nobody reads XML daily. So this
prints one row per sending source — IP, count, SPF, DKIM, and the policy that was
applied — and one verdict.

THE DISTINCTION THAT MATTERS, and the one a plausible-looking parser gets wrong:
**DMARC evaluates ALIGNMENT, not raw authentication.** A message can carry `spf=pass`
in `auth_results` and still fail DMARC, because the domain that authenticated is not the
domain in `header_from`. So the columns that decide the verdict come from
`row/policy_evaluated`, and `auth_results` is shown beside them as context — it is the
evidence for WHY something failed, never the answer to whether it did.

Schema quoted from RFC 7489 Appendix C, verified 18 Sep 2026 (docs/verified.md).

Exit codes: 0 everything aligned, 1 something did not, 2 this is not a DMARC report.
"""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger("dmarc_report")

ALIGNED = "pass"


@dataclass(frozen=True)
class Source:
    ip: str
    count: int
    spf: str
    dkim: str
    disposition: str
    spf_domain: str
    dkim_domain: str

    @property
    def aligned(self) -> bool:
        """Both from policy_evaluated. DMARC passes when EITHER aligns, but a source
        where one of them fails is still worth a human's attention before the policy
        moves to reject, so this reports strictly and the verdict counts strictly."""
        return self.spf == ALIGNED and self.dkim == ALIGNED

    def line(self) -> str:
        mark = "ok  " if self.aligned else "FAIL"
        return (
            f"  {mark} {self.ip:<16} {self.count:>6}  spf={self.spf:<9} dkim={self.dkim:<9}"
            f" policy={self.disposition:<10} auth: spf {self.spf_domain}, dkim {self.dkim_domain}"
        )


def text(node, path: str, default: str = "-") -> str:
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else default


def load(path: Path) -> ElementTree.Element:
    """A zip, a gzip, or bare XML. Google sends the first; a tool that only takes the
    third makes somebody unzip a file by hand every day, which is how it stops
    being used."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise ValueError(f"{path.name} is a zip with no .xml inside")
            data = zf.read(names[0])
    elif path.suffix == ".gz":
        import gzip

        data = gzip.decompress(path.read_bytes())
    else:
        data = path.read_bytes()
    root = ElementTree.fromstring(data)
    if root.tag != "feedback":
        raise ValueError(f"root element is <{root.tag}>, not <feedback>: not a DMARC report")
    return root


def sources(root: ElementTree.Element) -> list[Source]:
    out = []
    for record in root.findall("record"):
        out.append(
            Source(
                ip=text(record, "row/source_ip"),
                count=int(text(record, "row/count", "0")),
                spf=text(record, "row/policy_evaluated/spf"),
                dkim=text(record, "row/policy_evaluated/dkim"),
                disposition=text(record, "row/policy_evaluated/disposition"),
                spf_domain=text(record, "auth_results/spf/domain"),
                dkim_domain=text(record, "auth_results/dkim/domain"),
            )
        )
    return out


def header(root: ElementTree.Element) -> str:
    domain = text(root, "policy_published/domain")
    policy = text(root, "policy_published/p")
    pct = text(root, "policy_published/pct", "100")
    org = text(root, "report_metadata/org_name")
    return f"{domain}  p={policy} pct={pct}  reported by {org}"


def verdict(found: list[Source]) -> tuple[str, int]:
    failing = [s for s in found if not s.aligned]
    total = sum(s.count for s in found)
    if not failing:
        return f"all aligned ({total} messages from {len(found)} source(s))", 0
    worst = max(failing, key=lambda s: s.count)
    failed = sum(s.count for s in failing)
    extra = f" and {len(failing) - 1} other source(s)" if len(failing) > 1 else ""
    return (
        f"{failed} messages failed alignment from {worst.ip}{extra} "
        f"({total} messages from {len(found)} source(s))",
        1,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a DMARC aggregate report.")
    parser.add_argument("report", type=Path, help="the .zip, .gz or .xml as it arrived")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    try:
        root = load(args.report)
    except (ValueError, ElementTree.ParseError, OSError) as exc:
        print(f"DMARC REPORT: cannot read {args.report.name}: {exc}")
        sys.exit(2)

    found = sources(root)
    print(f"DMARC REPORT: {header(root)}\n")
    for source in sorted(found, key=lambda s: -s.count):
        print(source.line())
    summary, code = verdict(found)
    print(f"\nDMARC REPORT: {summary}")
    sys.exit(code)


if __name__ == "__main__":
    main()
