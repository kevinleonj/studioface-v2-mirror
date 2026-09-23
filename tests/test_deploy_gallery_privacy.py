"""Task 95g: the gallery privacy check runs on every deploy, after the funnel check.

scripts/check_gallery_privacy.py proves from outside that a gallery link's key never
reaches an address bar, a Referer or Google Analytics (task 31). Until now it ran only
when someone remembered to run it by hand, so a regression could ship and stay live.
It now runs in the deploy job straight after verify_production.py, against the same
public hostname, and a red result fails the deploy - no continue-on-error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"


def _steps() -> list[dict]:
    return yaml.safe_load(DEPLOY.read_text(encoding="utf-8"))["jobs"]["deploy"]["steps"]


def _index(steps: list[dict], script: str) -> int:
    found = [i for i, s in enumerate(steps) if script in str(s.get("run", ""))]
    assert len(found) == 1, f"{script}: expected one step in the deploy job, found {found}"
    return found[0]


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_the_gallery_privacy_check_runs_in_the_deploy_job():
    _index(_steps(), "scripts/check_gallery_privacy.py")


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_it_runs_after_the_funnel_check():
    steps = _steps()
    assert _index(steps, "scripts/check_gallery_privacy.py") > _index(
        steps, "scripts/verify_production.py"
    )


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_a_red_result_fails_the_deploy():
    """Must be refused: continue-on-error, or an `if:` that could skip it."""
    step = _steps()[_index(_steps(), "scripts/check_gallery_privacy.py")]
    assert not step.get("continue-on-error"), step
    assert "if" not in step, step


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_it_checks_the_public_hostname_like_the_funnel_check():
    step = _steps()[_index(_steps(), "scripts/check_gallery_privacy.py")]
    assert '"https://${{ vars.PUBLIC_DOMAIN }}"' in step["run"], step["run"]
