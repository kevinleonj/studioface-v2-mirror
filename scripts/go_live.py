"""Go-live preflight. Checks everything, changes nothing.

docs/GO-LIVE.md ends with a rule this script obeys rather than works around:

    It does not automate itself. A go-live that runs unattended is a go-live nobody
    read the plan for.

So this is the checking half only. It answers "is every precondition true right now",
prints the ordered command list with a verdict against each step, and stops. Running it
without --dry-run refuses, because the only safe default for a script called go_live is
to do nothing.

What it deliberately cannot do, enforced by tests/test_go_live.py against the argv lists
in this file rather than against its prose: apply infrastructure, deploy, set a CI
secret or variable, add a secret version, or push. It reads secret NAMES and never a
value — not even a prefix.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._exec import resolve  # noqa: E402

logger = logging.getLogger("go_live")

ROOT = Path(__file__).resolve().parents[1]
GO_LIVE = ROOT / "docs" / "GO-LIVE.md"
EXPORT = ROOT / "frontend" / "out"
PROJECT = "studio-face-fresh-start"
SITE = "https://studioface.app"
TIMEOUT_S = 30
# The SECOND-generation live objects task 07 created (docs/HANDOFF.md, task 07 entry).
# Not a secret: a Stripe object id, same class of value docs/stripe-test-objects.md
# already records in the clear.
CURRENT_LIVE_PRODUCT = "prod_VISvkPEoVJ3lPM"

OK, NO, UNKNOWN = "ok", "NO", "??"
# Listed, never blocking: an issue the 'after launch' label kept out of the verdict.
PARKED = "--"


@dataclass
class Check:
    mark: str
    name: str
    detail: str

    @property
    def blocking(self) -> bool:
        return self.mark == NO


def sh(argv: list[str]) -> tuple[int, str]:
    """Read-only by construction: every argv in this file is a list, and the tests
    assert none of them can spell a mutating command.

    resolve() takes the whole argv and returns it with argv[0] replaced, because on
    Windows CreateProcess does not search PATHEXT. It raises when the tool is absent,
    and a missing tool here is an UNKNOWN check rather than a crash — a preflight that
    dies on the first machine without gcloud tells you nothing about the other checks."""
    try:
        resolved = resolve(argv)
    except FileNotFoundError as exc:
        return 127, str(exc)
    try:
        r = subprocess.run(resolved, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return 124, f"{argv[0]} timed out after {TIMEOUT_S}s"
    return r.returncode, (r.stdout or r.stderr).strip()


# ---------------------------------------------------------------- the checks


def check_tree() -> list[Check]:
    code, branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    on_main = code == 0 and branch == "main"
    _, dirty = sh(["git", "status", "--porcelain"])
    return [
        Check(OK if on_main else NO, "on main", branch or "unknown"),
        Check(OK if not dirty else NO, "working tree clean", dirty.splitlines()[:1] or ["clean"]),
    ]


def check_ci() -> list[Check]:
    # --workflow, not just --limit 1. self-heal.yml is armed on every push and reports
    # "skipped" when the deploy succeeded, so the most recent run on main is almost
    # always a skipped heal — and reading that as the CI verdict says the deploy failed
    # every single time it worked.
    code, out = sh(
        [
            "gh",
            "run",
            "list",
            "--branch",
            "main",
            "--workflow",
            "deploy.yml",
            "--limit",
            "1",
            "--json",
            "conclusion,headSha",
        ]
    )
    if code != 0:
        return [Check(UNKNOWN, "CI green on HEAD", out[:70])]
    try:
        row = json.loads(out)[0]
    except (json.JSONDecodeError, IndexError):
        return [Check(UNKNOWN, "CI green on HEAD", "no runs")]
    _, head = sh(["git", "rev-parse", "HEAD"])
    same = row.get("headSha") == head
    green = row.get("conclusion") == "success"
    return [
        Check(OK if green else NO, "CI green", str(row.get("conclusion"))),
        Check(OK if same else NO, "CI ran on HEAD", row.get("headSha", "")[:8]),
    ]


def check_secrets() -> list[Check]:
    """NAMES ONLY. The value is never ours to read."""
    code, out = sh(["gcloud", "secrets", "list", "--project", PROJECT, "--format", "value(name)"])
    if code != 0:
        return [Check(UNKNOWN, "secrets exist", out[:70])]
    have = set(out.split())
    return [
        Check(OK if name in have else NO, f"secret {name} exists", "name only, never the value")
        for name in ("stripe-secret-key", "stripe-webhook-secret")
    ]


def check_stripe_state() -> list[Check]:
    """The two-prefix plan (a second Terraform state under prefix=studioface-live) was
    withdrawn before task 07 ran (docs/GO-LIVE.md: "That plan is withdrawn"). There is
    one state, and the live switch works by `terraform state rm` on the four Stripe
    addresses in it, then an ordinary apply recreates them live. So the thing worth
    checking now is not "is a second prefix empty" (it always will be; nothing ever
    writes there) but "does the one state currently track the CURRENT live objects" —
    catches the state drifting back to an orphaned generation, read-only, via
    `terraform state show` (no provider credentials needed; this is a state read, not
    a provider refresh, so it never touches the live Stripe key)."""
    code, out = sh(
        ["terraform", "-chdir=infra", "state", "show", "-no-color", "stripe_product.headshots"]
    )
    if code != 0:
        return [Check(UNKNOWN, "Stripe product tracked in state", out[:70])]
    match = next((ln for ln in out.splitlines() if ln.strip().startswith("id ")), "")
    tracked = match.split("=", 1)[-1].strip().strip('"') if "=" in match else ""
    return [
        Check(
            OK if tracked == CURRENT_LIVE_PRODUCT else NO,
            "Stripe state tracks the current live product",
            tracked or "not found",
        )
    ]


def check_refund_events() -> list[Check]:
    """Step 11b: Bizum refunds settle asynchronously, so without these two events the
    order status lies about money that has not moved."""
    tf = (ROOT / "infra" / "stripe.tf").read_text(encoding="utf-8", errors="ignore")
    missing = [e for e in ("refund.updated", "refund.failed") if e not in tf]
    return [
        Check(
            OK if not missing else NO,
            "refund events declared in infra/stripe.tf",
            "both present" if not missing else f"missing {missing}",
        )
    ]


def check_production() -> list[Check]:
    code, out = sh(["curl", "-s", "--max-time", "10", f"{SITE}/health"])
    if code != 0:
        return [Check(UNKNOWN, "production healthy", out[:70])]
    try:
        body = json.loads(out)
    except json.JSONDecodeError:
        return [Check(NO, "production healthy", out[:70])]
    return [
        Check(OK if body.get("ok") else NO, "production healthy", json.dumps(body)),
        Check(
            OK if not body.get("killswitch") else NO,
            "kill switch off",
            f"killswitch={body.get('killswitch')}",
        ),
    ]


def check_export() -> list[Check]:
    if not (EXPORT / "index.html").exists():
        return [Check(NO, "frontend built", "frontend/out is missing")]
    html = (EXPORT / "index.html").read_text(encoding="utf-8", errors="ignore")
    return [
        Check(OK, "frontend built", "frontend/out/index.html present"),
        Check(
            # Task 96a: the registered name as well as the NIF. The NIF alone passed
            # under the wrong name (limeralda) for a week.
            OK if "Z3714124-C" in html and "Kevin Daniel León Jouvin" in html else NO,
            "trader identity on the landing page",
            "LSSI-CE Art. 10",
        ),
    ]


AFTER_LAUNCH = "after launch"


def _parked(row: dict) -> bool:
    """True when someone decided this issue does not have to be true before an ad runs.

    The label is the record of that decision, so it is read rather than re-argued here.
    Fails CLOSED: a row with no `labels` field at all - a gh output shape change, say -
    counts as unlabelled and keeps blocking, because waving issues through on a parsing
    accident is the one failure this check must not have.
    """
    return any(label.get("name") == AFTER_LAUNCH for label in row.get("labels") or [])


def check_blocking_issues() -> list[Check]:
    code, out = sh(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--json",
            "number,title,labels",
            "--limit",
            "50",
        ]
    )
    if code != 0:
        return [Check(UNKNOWN, "no blocking issues", out[:70])]
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return [Check(UNKNOWN, "no blocking issues", out[:70])]
    blocking = [
        f"#{r['number']}" for r in rows if "go live" not in r["title"].lower() and not _parked(r)
    ]
    # Task 91: the label decides what blocks a launch, and a label added by habit rather
    # than by decision would otherwise vanish from every run. Each one is printed, number
    # and title, so it is re-read every time the preflight is.
    parked = [
        Check(PARKED, "parked 'after launch', not blocking", f"#{r['number']} {r['title']}")
        for r in rows
        if _parked(r)
    ]
    return [
        Check(
            OK if not blocking else NO,
            "no open needs-Kevin issues",
            ", ".join(blocking) or "none",
        ),
        *parked,
    ]


CHECKS = (
    check_tree,
    check_export,
    check_ci,
    check_secrets,
    check_stripe_state,
    check_refund_events,
    check_production,
    check_blocking_issues,
)


# ---------------------------------------------------------------- reporting


def steps() -> list[tuple[str, str]]:
    """The ordered command list, read from GO-LIVE.md rather than copied, so the two
    cannot drift. A preflight that checks a procedure it has its own copy of is
    checking its own copy."""
    out = []
    for line in GO_LIVE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| #"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].rstrip("b").isdigit():
            out.append((cells[0], cells[1]))
    return out


def refuse() -> None:
    print("go_live.py runs with --dry-run and nothing else.")
    print()
    print("There is no execute mode, on purpose. docs/GO-LIVE.md: 'It does not automate")
    print("itself. A go-live that runs unattended is a go-live nobody read the plan for.'")
    print("This script tells you whether every precondition holds. You run the steps.")
    sys.exit(2)


def verdict(results: list[Check]) -> int:
    """An unanswered check blocks exactly like a failed one. 'I could not tell' is not
    a pass, and treating it as one is how a preflight becomes decoration."""
    blocked = [c for c in results if c.blocking]
    unknown = [c for c in results if c.mark == UNKNOWN]
    print()
    if blocked:
        print(f"GO-LIVE PREFLIGHT: BLOCKED by {len(blocked)} check(s)")
    elif unknown:
        print(f"GO-LIVE PREFLIGHT: BLOCKED, {len(unknown)} check(s) could not be answered")
    else:
        print("GO-LIVE PREFLIGHT: READY. Every precondition holds; the steps are still yours.")
        # On READY only: that is the verdict a parked issue can have changed, and the
        # verdict line is the one people read.
        parked = [c for c in results if c.mark == PARKED]
        if parked:
            print(f"  {len(parked)} issue(s) parked 'after launch', listed above. Re-read them.")
        return 0
    for c in blocked + unknown:
        print(f"  - {c.name}: {c.detail}")
    return 1


def main() -> None:
    if "--dry-run" not in sys.argv[1:]:
        refuse()

    print("GO-LIVE PREFLIGHT — reads everything, changes nothing\n")
    results: list[Check] = []
    for check in CHECKS:
        results.extend(check())
    for c in results:
        print(f"  {c.mark} {c.name}: {c.detail}")

    print("\nTHE PROCEDURE (docs/GO-LIVE.md). Every step is yours to run.\n")
    for number, what in steps():
        print(f"  {number}. {what}")

    sys.exit(verdict(results))


if __name__ == "__main__":
    main()
