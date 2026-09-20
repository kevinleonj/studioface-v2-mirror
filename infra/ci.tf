# GitOps: GitHub Actions applies this Terraform and deploys. The deployer service account
# therefore needs to manage everything in this project, plus the budget on the billing
# account. These bindings are applied ONCE locally by bootstrap.py; after that, CI applies
# every later change.
#
# It held roles/owner until 18 Sep 2026. Owner permitted reading every secret's VALUE,
# deleting the Firestore database, deleting the buckets holding customers' photographs,
# granting itself any role and removing Kevin's own access — from a credential reachable
# by a GitHub Actions workflow. It now holds the eleven roles below and nothing more.
resource "google_billing_account_iam_member" "deployer_budgets" {
  for_each           = toset(["roles/billing.viewer", "roles/billing.costsManager"])
  billing_account_id = var.billing_account
  role               = each.value
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# ---------------------------------------------------------------- narrowing owner
#
# BOTH PHASES ARE NOW DONE. These are the roles Terraform actually needs, derived from the
# resource types declared in infra/*.tf rather than from a wishlist, and every name
# checked against the live catalogue with `gcloud iam roles describe` - a typo here is an
# apply failure, and the list is long.
#
# They were granted ADDITIVELY first, in a separate apply, while roles/owner was still in
# place. That split was deliberate: Terraform uses these permissions to change these
# permissions, so removing owner in the same apply that grants the replacements risks the
# replacements landing after the removal, and an apply that half-finishes leaves a
# pipeline that cannot fix itself. Phase one proved the list was real and grantable;
# this apply removes owner with the replacements already in force for its whole duration.
#
# ROLLBACK, if an apply ever fails for want of a permission. Runnable by Kevin, who holds
# owner as a user:
#
#   gcloud projects add-iam-policy-binding studio-face-fresh-start #     --member=serviceAccount:sa-studioface-deployer@studio-face-fresh-start.iam.gserviceaccount.com #     --role=roles/owner
#
# What owner currently permits that none of these do: reading every secret's VALUE,
# deleting the Firestore database, deleting the buckets holding customers' photographs,
# and removing Kevin's own access. That is the blast radius of a compromised workflow.
resource "google_project_iam_member" "deployer_terraform" {
  for_each = toset([
    "roles/serviceusage.serviceUsageAdmin",    # google_project_service
    "roles/resourcemanager.projectIamAdmin",   # google_project_iam_member
    "roles/iam.serviceAccountAdmin",           # google_service_account (+ its iam_member)
    "roles/iam.workloadIdentityPoolAdmin",     # google_iam_workload_identity_pool (+ provider)
    "roles/secretmanager.admin",               # google_secret_manager_secret (+ versions)
    "roles/storage.admin",                     # google_storage_bucket
    "roles/datastore.owner",                   # google_firestore_database
    "roles/cloudtasks.admin",                  # google_cloud_tasks_queue
    "roles/run.admin",                         # google_cloud_run_v2_service (+ iam, domain mapping)
    "roles/artifactregistry.admin",            # google_artifact_registry_repository
    "roles/pubsub.admin",                      # google_pubsub_topic (+ subscription)
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}
