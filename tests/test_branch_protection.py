"""main is the deploy log. A force push to it rewrites what was deployed.

Applied by hand first, tested with a real push, then written into infra/github.tf so it
cannot drift back off. This file asserts the Terraform, because the Terraform is what
survives somebody clicking in the GitHub UI.

The interesting half is what is deliberately NOT on. Required status checks were enabled,
measured and removed:

    $ git push origin main          # with ci, design, emulator required
    remote: - 3 of 3 required status checks are expected.
    7d2625c..278122d  main -> main          # succeeded anyway

`enforce_admins` is false, so an admin push warns and proceeds. For us they therefore
protect nothing — with one exception, and it is the exception that decides it.
`self-heal.yml` pushes a fix as a GitHub App, which is not an admin, and it runs ONLY
when the checks are red. Requiring green checks before that push means the healer can
never push. The control would block exactly the actor we need it not to block, and
nobody else.

Having both is possible with a ruleset that names the healer as a bypass actor. That is
a different GitHub feature and a separate change.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GITHUB_TF = ROOT / "infra" / "github.tf"
HEAL = ROOT / ".github" / "workflows" / "self-heal.yml"


def protection() -> str:
    text = GITHUB_TF.read_text(encoding="utf-8")
    block = re.search(r'resource "github_branch_protection" "main" \{(.*?)\n\}', text, re.S)
    assert block, "main is not protected in infra/github.tf"
    return block.group(1)


def setting(name: str) -> str:
    found = re.search(rf"^\s*{name}\s*=\s*(\S+)", protection(), re.M)
    assert found, f"{name} is not set"
    return found.group(1)


def test_main_is_protected_in_terraform_not_only_in_the_ui():
    """A rule applied by hand is a rule one click removes, with no diff to review."""
    assert protection()
    assert re.search(r'pattern\s*=\s*"main"', protection())


def test_force_pushes_are_blocked():
    """The history IS the deploy log. A force push rewrites what was deployed, and the
    self-healer's account of what it fixed goes with it."""
    assert setting("allows_force_pushes") == "false"


def test_deletions_are_blocked():
    assert setting("allows_deletions") == "false"


def test_linear_history_is_required():
    """Every commit on main is a deploy. A merge commit makes "which commit is live"
    ambiguous in the one place it must not be."""
    assert setting("required_linear_history") == "true"


def test_required_status_checks_are_absent_and_the_reason_is_written_down():
    """Held-out check, and the point of the whole file.

    This is the setting somebody adds later because it sounds obviously good. It is not:
    it blocks the healer and nobody else. The assertion is paired with a demand that the
    reason stays next to it, because an unexplained absence gets 'fixed'."""
    body = protection()
    assert "required_status_checks" not in body, (
        "required status checks block self-heal, which pushes as a GitHub App precisely "
        "when the checks are red"
    )
    comment = GITHUB_TF.read_text(encoding="utf-8")
    assert "self-heal" in comment, "the reason for the absence is not recorded beside it"


def test_the_healer_really_does_push_to_main_so_the_reason_is_not_hypothetical():
    """If self-heal stops pushing, the argument above expires and required status checks
    should be reconsidered. This fails when that day comes."""
    assert HEAL.exists(), "self-heal.yml is gone; re-open the required-checks decision"
    body = HEAL.read_text(encoding="utf-8")
    assert "push" in body, "self-heal no longer pushes; re-open the required-checks decision"


def test_the_rule_is_adopted_rather_than_recreated():
    """The red deploy I caused: the rule was applied by hand to test it, then written
    into Terraform without telling Terraform it existed.

        Error: Name already protected: main

    Deleting the rule so Terraform could recreate it would leave main unprotected for the
    length of a deploy. An import block adopts it instead - declarative, visible in the
    diff, and a no-op once state holds it."""
    text = GITHUB_TF.read_text(encoding="utf-8")
    # Not `[^}]*`: the id is "${var.repo_name}:main" and the interpolation's own closing
    # brace ends the match early, so the assertion below failed on a correct file.
    block = re.search(r"import \{(.*?)\n\}", text, re.S)
    assert block, "the hand-applied rule is not adopted, so the apply will fail again"
    assert "github_branch_protection.main" in block.group(1)
    assert ":main" in block.group(1), "the import id is not repository:pattern"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
