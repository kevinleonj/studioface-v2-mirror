"""Who is allowed to write each Secret Manager secret. One writer each, no exceptions.

I reported in 92e332c that stripe-webhook-secret had TWO writers, Terraform and
bootstrap. That was wrong. bootstrap writes USER_SECRETS plus app-token-secret and
tasks-token, and has never written stripe-webhook-secret or turnstile-secret;
Terraform has always been their sole owner.

The real hazard is worse, because it is automatic and recurring rather than a
one-off during setup:

    google_secret_manager_secret_version.stripe_webhook
        secret_data = stripe_webhook_endpoint.api.secret

and deploy.yml runs `terraform apply` on EVERY push to main. The secret always holds
whatever the applied state's webhook endpoint is. Today that is correct, because the
only state is the test one. After go-live it is a trap: the live endpoint's whsec_
goes into the secret by hand or by the live state, and then the next ordinary
deploy — any deploy, a README typo — silently puts the TEST secret back as the newest
version. Cloud Run reads `latest`, verify_stripe_signature then rejects every live
event with 400, no order is ever created, and Stripe retries into a wall. Nothing in
the service logs an error, because from its side no webhook ever arrived.

These tests pin sole ownership. They passed the first time they ran: the premise of
the fix was wrong, so there is nothing to repair, only something to hold still.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GCP_TF = (ROOT / "infra" / "gcp.tf").read_text(encoding="utf-8")

# Terraform's, and only Terraform's. Both derive from a vendor resource in the same
# state, so a human or a script writing them would be writing a value Terraform owns.
TERRAFORM_OWNED = ("stripe-webhook-secret", "turnstile-secret")

# Everything bootstrap is allowed to put. Anything else appearing in bootstrap is
# either a new secret nobody documented or an encroachment on the list above.
BOOTSTRAP_OWNED = {
    "fal-key",
    "stripe-secret-key",
    "resend-api-key",
    "ga4-api-secret",
    "app-token-secret",
    "tasks-token",
}


def bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_mod", ROOT / "bootstrap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bootstrap_does_not_write_the_terraform_owned_secrets():
    """The pin Kevin asked for. It holds today; it is here so it keeps holding."""
    names = set(bootstrap().USER_SECRETS)
    for secret in TERRAFORM_OWNED:
        assert secret not in names, f"bootstrap must not write {secret}; Terraform owns it"


def test_bootstrap_writes_nothing_beyond_its_own_list():
    """Held-out check, and the one with teeth: USER_SECRETS is not the only way
    bootstrap can write a secret — it also calls put_secret() directly for the two it
    generates. A future put_secret("stripe-webhook-secret", ...) would sail past the
    test above. This reads the source for every literal handed to put_secret."""
    text = (ROOT / "bootstrap.py").read_text(encoding="utf-8")
    literals = set(re.findall(r'put_secret\(\s*[^,]+,\s*"([^"]+)"', text))
    assert literals, "no direct put_secret calls found — has the call shape changed?"
    assert literals <= BOOTSTRAP_OWNED, f"bootstrap writes undeclared secrets: {literals}"
    for secret in TERRAFORM_OWNED:
        assert secret not in literals


def test_terraform_declares_exactly_one_version_resource_for_each():
    for secret in TERRAFORM_OWNED:
        key = secret.replace("-", "_").replace("stripe_webhook_secret", "stripe_webhook")
        hits = re.findall(r'google_secret_manager_secret_version"\s+"(\w+)"', GCP_TF)
        assert hits, "no secret version resources in infra/gcp.tf"
        assert len(hits) == len(set(hits)), f"duplicate version resources: {hits}"
        assert any(h in key or key.startswith(h) for h in hits), f"{secret} has no owner"


@pytest.mark.mirror_incompatible(reason="reads .github/workflows, which the mirror does not carry")
def test_the_version_resource_tracks_the_endpoint_in_the_applied_state():
    """This is the go-live trap, asserted rather than only described in prose. The
    secret's value follows whichever webhook endpoint the applied state holds, and CI
    applies the TEST state on every push."""
    assert re.search(
        r'resource\s+"google_secret_manager_secret_version"\s+"stripe_webhook"\s*\{[^}]*'
        r"secret_data\s*=\s*stripe_webhook_endpoint\.api\.secret",
        GCP_TF,
        re.S,
    ), "stripe_webhook version no longer derives from stripe_webhook_endpoint.api"

    deploy = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "terraform -chdir=infra apply" in deploy, (
        "if CI no longer applies Terraform on every push, docs/GO-LIVE.md section 4 "
        "is describing a hazard that no longer exists — update it"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
