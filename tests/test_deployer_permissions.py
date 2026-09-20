"""The deployer service account holds roles/owner. That is the largest blast radius we own.

Owner on the project means: read every secret's value, delete the Firestore database,
delete the buckets holding customers' photographs, grant itself anything, and remove
Kevin. It is held by a service account whose credentials are reachable from a GitHub
Actions workflow, so the real question is what a compromised workflow could do, and the
answer today is everything.

**Done in two applies, and the split was deliberate rather than timid.** Terraform uses
these very permissions to change these very permissions. Removing owner in the same apply
that grants the replacements means the replacements might land after the removal, and an
apply that half-finishes leaves a pipeline that cannot fix itself. So:

    phase 1   granted the narrow roles ADDITIVELY. Could not break anything: the SA still
              had owner throughout. Proved every role name was real and grantable, and
              that an apply succeeds with them present. Verified live afterwards.
    phase 2   removed roles/owner, with the replacements already in force for the whole
              of that apply.

Every role below was checked against the live IAM catalogue with `gcloud iam roles
describe` — a typo in a role name is an apply failure, and the list is long.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CI_TF = ROOT / "infra" / "ci.tf"

# One role per thing Terraform actually manages, derived from the resource types in
# infra/*.tf rather than from a wishlist. Each name verified to exist, 18 Sep 2026.
REQUIRED = {
    "roles/serviceusage.serviceUsageAdmin": "google_project_service",
    "roles/resourcemanager.projectIamAdmin": "google_project_iam_member",
    "roles/iam.serviceAccountAdmin": "google_service_account",
    "roles/iam.workloadIdentityPoolAdmin": "google_iam_workload_identity_pool",
    "roles/secretmanager.admin": "google_secret_manager_secret",
    "roles/storage.admin": "google_storage_bucket",
    "roles/datastore.owner": "google_firestore_database",
    "roles/cloudtasks.admin": "google_cloud_tasks_queue",
    "roles/run.admin": "google_cloud_run_v2_service",
    "roles/artifactregistry.admin": "google_artifact_registry_repository",
    "roles/pubsub.admin": "google_pubsub_topic",
}


def ci_tf() -> str:
    return CI_TF.read_text(encoding="utf-8")


def granted() -> set[str]:
    block = re.search(r'"deployer_terraform"\s*\{(.*?)\n\}', ci_tf(), re.S)
    assert block, "the narrow role set is not declared"
    return set(re.findall(r'"(roles/[\w.]+)"', block.group(1)))


def test_every_resource_type_terraform_manages_has_a_role_that_can_manage_it():
    missing = sorted(set(REQUIRED) - granted())
    assert not missing, f"Terraform manages resources it would have no role for: {missing}"


def test_the_role_list_is_derived_from_what_is_actually_managed():
    """Held-out check against the opposite failure: a list padded with roles nothing
    needs is a list nobody trimmed, and it re-creates owner one grant at a time."""
    extra = sorted(granted() - set(REQUIRED))
    assert not extra, f"roles granted that no resource in infra/ requires: {extra}"


def test_every_google_resource_type_in_infra_is_accounted_for():
    """The list above is only honest if it covers what infra/ actually declares. This
    fails when somebody adds a resource type and not the role that manages it."""
    declared = set()
    for path in sorted((ROOT / "infra").glob("*.tf")):
        declared |= set(
            re.findall(
                r'^resource "(google[a-z_]*_[a-z0-9_]+)"', path.read_text(encoding="utf-8"), re.M
            )
        )
    # These are covered by a role already listed for their parent resource type, or by
    # the billing-account bindings, which live on a different resource entirely.
    covered_elsewhere = {
        "google_service_account_iam_member",  # iam.serviceAccountAdmin
        "google_iam_workload_identity_pool_provider",  # iam.workloadIdentityPoolAdmin
        "google_secret_manager_secret_version",  # secretmanager.admin
        "google_cloud_run_v2_service_iam_member",  # run.admin
        "google_cloud_run_domain_mapping",  # run.admin
        "google_pubsub_subscription",  # pubsub.admin
        "google_billing_budget",  # billing.costsManager, on the billing account
        "google_billing_account_iam_member",  # billing account, not the project
    }
    unaccounted = sorted(declared - set(REQUIRED.values()) - covered_elsewhere)
    assert not unaccounted, f"resource types with no role mapped: {unaccounted}"


def test_owner_is_gone():
    """Phase two. This is the whole point of the file.

    roles/owner permitted reading every secret's VALUE, deleting the Firestore database,
    deleting the buckets holding customers' photographs, granting itself any role and
    removing Kevin's own access — from a credential a GitHub Actions workflow can reach.

    If an apply ever fails for want of a permission, the answer is to add the ONE role
    that was missing, not to put owner back. The rollback exists for an emergency, and an
    emergency rollback that becomes permanent is how this started."""
    assert '"roles/owner"' not in ci_tf(), "the deployer holds owner again"


def test_the_rollback_is_recorded_beside_the_change():
    """A permission narrowing with no way back is one somebody reverts by guessing."""
    text = ci_tf()
    assert "add-iam-policy-binding" in text, "no rollback command beside the change"
    assert "ROLLBACK" in text


def test_the_reasoning_survives_where_the_next_person_will_look():
    """A narrowed permission set with no note reads as an arbitrary list, and arbitrary
    lists get widened by the next person who hits a permission error."""
    assert "phase" in ci_tf().lower(), "the two-apply reasoning is not in infra/ci.tf"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
