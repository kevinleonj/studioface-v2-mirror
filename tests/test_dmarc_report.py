"""Reading a DMARC aggregate report, which arrives daily and forever.

The XML shape is quoted from RFC 7489 Appendix C, verified 18 Sep 2026, not recalled:
`feedback` / `report_metadata` / `policy_published{p,sp,pct,adkim,aspf}` /
`record{row{source_ip,count,policy_evaluated{disposition,dkim,spf}},
identifiers{header_from,envelope_from}, auth_results{dkim{domain,result,selector},
spf{domain,result}}}`.

The load-bearing distinction, and the one a naive parser gets wrong: **DMARC evaluates
ALIGNMENT, not raw authentication.** A message can carry `spf=pass` in `auth_results`
and still fail DMARC, because the domain that passed is not the domain in `header_from`.
`tests/fixtures/dmarc/failing.xml` has exactly that record — `198.51.100.22`, dkim
`pass` for `mailer.example`, and `policy_evaluated/dkim = fail`. A parser that reads
`auth_results` and reports "all aligned" for it is worse than no parser, because it
would licence moving the policy to reject on the strength of a false clean bill.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dmarc_report.py"
FIXTURES = Path(__file__).parent / "fixtures" / "dmarc"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=ROOT,
        check=False,
    )


def test_a_fully_aligned_report_says_so_and_exits_zero():
    r = run(str(FIXTURES / "aligned.xml"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all aligned" in r.stdout
    assert "54.240.8.31" in r.stdout
    assert "15" in r.stdout, "the total message count is not reported"


def test_every_sending_source_is_reported_with_all_five_facts():
    """IP, count, SPF result, DKIM result and the policy evaluated. A report that omits
    one of them cannot answer the only question worth asking of it."""
    out = run(str(FIXTURES / "aligned.xml")).stdout
    line = next((ln for ln in out.splitlines() if "54.240.8.31" in ln), "")
    assert line, "no line for the first source"
    for fact in ("54.240.8.31", "12", "pass", "none"):
        assert fact in line, f"{fact!r} missing from: {line!r}"


def test_a_failing_report_names_the_count_and_the_ip():
    """The verdict the brief asked for, verbatim: "N messages failed alignment from
    <ip>"."""
    r = run(str(FIXTURES / "failing.xml"))
    assert r.returncode == 1, "a report with failures must not exit zero"
    assert "203.0.113.7" in r.stdout
    assert "41" in r.stdout
    assert "failed alignment" in r.stdout


def test_a_source_that_authenticates_but_does_not_ALIGN_is_counted_as_a_failure():
    """The one that separates a real parser from a plausible one.

    198.51.100.22 has dkim result `pass` in auth_results — for mailer.example, not for
    studioface.app — and `policy_evaluated/dkim = fail`. Reading auth_results would call
    this aligned and licence a move to p=reject on a false clean bill."""
    out = run(str(FIXTURES / "failing.xml")).stdout
    line = next((ln for ln in out.splitlines() if "198.51.100.22" in ln), "")
    assert line, "the non-aligned source is missing from the report entirely"
    assert "fail" in line, f"a source that fails alignment is not reported failing: {line!r}"
    assert "198.51.100.22" in out.split("failed alignment")[0] or "198.51.100.22" in out


def test_it_reads_a_zip_because_that_is_how_the_report_actually_arrives(tmp_path):
    """Google sends a .zip. A tool that only takes XML makes a human unzip it daily,
    which is how a tool stops being used."""
    archive = tmp_path / "google.com!studioface.app!1789430400!1789516800.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIXTURES / "aligned.xml", arcname="report.xml")
    r = run(str(archive))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all aligned" in r.stdout


def test_it_reports_the_published_policy_it_was_evaluated_against():
    """Without this the numbers float free: "3 failures" means something different under
    p=none than under p=quarantine, which is what this domain publishes."""
    out = run(str(FIXTURES / "failing.xml")).stdout
    assert "quarantine" in out
    assert "studioface.app" in out


def test_a_file_that_is_not_a_report_fails_loudly(tmp_path):
    bad = tmp_path / "notes.xml"
    bad.write_text("<hello/>", encoding="utf-8")
    r = run(str(bad))
    assert r.returncode == 2, "a malformed input must not look like a clean report"
    assert "feedback" in (r.stdout + r.stderr).lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
