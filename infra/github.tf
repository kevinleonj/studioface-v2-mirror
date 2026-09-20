resource "github_repository" "repo" {
  name        = var.repo_name
  visibility  = "private"
  auto_init   = false
  description = "StudioFace v2: AI headshots for Spain. GCP + fal.ai + Stripe."
  # The escalation channel. Every rule that says "needs money, credentials or a console
  # action -> open an issue titled needs Kevin: <what>" — including self-heal.yml's
  # prompt — depends on this. The provider defaults it to false, so it was closed.
  has_issues = true
}
# Branch protection on main. Applied by hand first and TESTED with a real push, then
# written here so it cannot drift back off.
#
# WHAT IS ON: force pushes blocked, deletions blocked, linear history required. Those are
# the ones that matter for a repository whose history IS the deploy log - a force push to
# main rewrites what was deployed, and a deletion loses it.
#
# WHAT IS DELIBERATELY OFF: required status checks. They were enabled, tested and removed,
# and the reason is circular rather than cosmetic. self-heal.yml pushes a fix as a GitHub
# App, and it pushes PRECISELY WHEN THE CHECKS ARE RED - that is the only time it runs.
# Requiring green checks before that push means the healer can never heal. Measured with
# the checks on: a push from an admin succeeds with `3 of 3 required status checks are
# expected`, because enforce_admins is false, so for us they warn and never block - except
# for the one actor they would block, which is the one we need.
#
# Having both needs a RULESET with the healer as a bypass actor, not classic protection.
# That is a separate change and is in HANDOFF as a follow-up.
# The rule already exists, because I applied it by hand to TEST it before writing it
# down - and then wrote it down without telling Terraform it was already there. The apply
# failed with `Error: Name already protected: main`, which is a red deploy I caused by
# doing the right verification in the wrong order. Under GitOps the rule goes into
# Terraform first and CI applies it; the hand-applied version is what needs adopting.
#
# An import block rather than deleting the rule and letting Terraform recreate it: that
# would leave main unprotected for the length of a deploy, and an import is declarative,
# reviewable in the diff, and idempotent once state holds it.
# ID format is `repository:pattern`, from the provider's own import documentation.
import {
  to = github_branch_protection.main
  id = "${var.repo_name}:main"
}

resource "github_branch_protection" "main" {
  repository_id                   = github_repository.repo.node_id
  pattern                         = "main"
  allows_force_pushes             = false
  allows_deletions                = false
  required_linear_history         = true
  enforce_admins                  = false
  require_conversation_resolution = false
}

resource "github_actions_variable" "vars" {
  for_each = {
    GCP_PROJECT_ID    = var.project_id
    GCP_REGION        = var.region
    GCP_WIF_PROVIDER  = google_iam_workload_identity_pool_provider.gh.name
    GCP_DEPLOYER_SA   = google_service_account.deployer.email
    CLOUD_RUN_SERVICE = google_cloud_run_v2_service.api.name
    AR_REPO           = google_artifact_registry_repository.img.repository_id
  }
  repository    = github_repository.repo.name
  variable_name = each.key
  value         = each.value
}
