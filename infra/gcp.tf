locals {
  services = [
    "iam.googleapis.com", "run.googleapis.com", "firestore.googleapis.com", "secretmanager.googleapis.com",
    "cloudtasks.googleapis.com", "artifactregistry.googleapis.com", "iamcredentials.googleapis.com",
    "sts.googleapis.com", "pubsub.googleapis.com", "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
  ]
  secret_ids = ["fal-key", "stripe-secret-key", "stripe-webhook-secret", "resend-api-key",
  "app-token-secret", "ga4-api-secret", "turnstile-secret", "tasks-token"]
}

resource "google_project_service" "svc" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- identity
resource "google_service_account" "api" {
  account_id   = "sa-studioface-api"
  display_name = "StudioFace API runtime"
}
resource "google_service_account" "deployer" {
  account_id   = "sa-studioface-deployer"
  display_name = "GitHub Actions deployer (WIF, no keys)"
}
resource "google_project_iam_member" "api_roles" {
  for_each = toset(["roles/datastore.user", "roles/cloudtasks.enqueuer",
    "roles/secretmanager.secretAccessor", "roles/storage.objectAdmin",
  "roles/iam.serviceAccountTokenCreator"])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}
resource "google_project_iam_member" "deployer_roles" {
  for_each = toset(["roles/run.admin", "roles/artifactregistry.writer", "roles/iam.serviceAccountUser"])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# GitHub Actions -> GCP without any JSON key (Workload Identity Federation)
resource "google_iam_workload_identity_pool" "gh" {
  workload_identity_pool_id = "github-pool"
  depends_on                = [google_project_service.svc] # needs iam.googleapis.com enabled first
}
resource "google_iam_workload_identity_pool_provider" "gh" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.gh.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  attribute_condition                = "attribute.repository == \"${var.github_owner}/${var.repo_name}\""
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gh.name}/attribute.repository/${var.github_owner}/${var.repo_name}"
}

# ---------------------------------------------------------------- secrets (containers only; values added by bootstrap via stdin)
resource "google_secret_manager_secret" "s" {
  for_each  = toset(local.secret_ids)
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.svc]
}

resource "google_secret_manager_secret_version" "stripe_webhook" {
  secret      = google_secret_manager_secret.s["stripe-webhook-secret"].id
  secret_data = stripe_webhook_endpoint.api.secret
}
resource "google_secret_manager_secret_version" "turnstile" {
  secret      = google_secret_manager_secret.s["turnstile-secret"].id
  secret_data = cloudflare_turnstile_widget.preview.secret
}

# ---------------------------------------------------------------- data
resource "google_firestore_database" "db" {
  name        = "(default)"
  location_id = "eur3"
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.svc]
}
resource "google_storage_bucket" "src" {
  name                        = "${var.project_id}-src"
  location                    = "EU"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }
}
resource "google_storage_bucket" "out" {
  name                        = "${var.project_id}-out"
  location                    = "EU"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  lifecycle_rule {
    condition { age = 365 }
    action { type = "Delete" }
  }
}
resource "google_cloud_tasks_queue" "gen" {
  name     = "generate"
  location = var.region
  rate_limits {
    max_concurrent_dispatches = 4
  }
  retry_config {
    max_attempts  = 5
    min_backoff   = "10s"
    max_backoff   = "300s"
    max_doublings = 4
  }
  depends_on = [google_project_service.svc]
}
resource "google_artifact_registry_repository" "img" {
  location      = var.region
  repository_id = "studioface"
  format        = "DOCKER"
  depends_on    = [google_project_service.svc]
}

# ---------------------------------------------------------------- compute
resource "google_cloud_run_v2_service" "api" {
  name     = "studioface-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  # Provider default is true and blocks the replace of a tainted (failed) service. The service
  # holds no data (Firestore + buckets do); CI redeploys it on every push, so recreate is safe.
  deletion_protection = false
  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    max_instance_request_concurrency = 4
    timeout                          = "300s"
    containers {
      # Placeholder image; deploy.yml replaces it on every push to main.
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "TASKS_QUEUE"
        value = google_cloud_tasks_queue.gen.name
      }
      env {
        name  = "BUCKET_SRC"
        value = google_storage_bucket.src.name
      }
      env {
        name  = "BUCKET_OUT"
        value = google_storage_bucket.out.name
      }
      # Who may push to /internal/budget, and the audience their token must carry. The
      # subscription below pins the same audience, so the two cannot drift apart.
      env {
        name  = "PUBSUB_PUSH_SA"
        value = google_service_account.api.email
      }
      env {
        name  = "PUBSUB_PUSH_AUDIENCE"
        value = "https://api.${var.domain}/internal/budget"
      }
      env {
        name  = "PUBLIC_URL"
        value = "https://${var.domain}"
      }
      env {
        name  = "PRICE_EUR_CENTS"
        value = tostring(var.price_eur_cents)
      }
      env {
        # POST /api/checkout needs the Terraform-managed price id (docs/DECISIONS.md).
        # app/config.py treats it as optional and the route answers 503 until this
        # reaches a revision, so code and infra can land in either order.
        name  = "STRIPE_PRICE_EUR"
        value = stripe_price.eur.id
      }
      env {
        # The Measurement Protocol backstop needs the ID as well as GA4_API_SECRET,
        # which already arrives as a secret. Optional in app/config.py: without it the
        # purchase event is skipped and logged, never an error.
        name  = "GA4_MEASUREMENT_ID"
        value = var.ga4_measurement_id
      }
      dynamic "env" {
        for_each = local.secret_ids
        content {
          name = upper(replace(env.value, "-", "_"))
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].containers[0].image] # CI owns the image
  }
  # Cloud Run validates every secret_key_ref at deploy time: a secret with no version, or one the
  # runtime service account cannot read yet, fails the revision. Bootstrap adds the user-provided
  # versions between phase A (-target) and phase B (full apply); these depends_on cover the rest.
  depends_on = [
    google_project_iam_member.api_roles,
    google_secret_manager_secret.s,
    google_secret_manager_secret_version.stripe_webhook,
    google_secret_manager_secret_version.turnstile,
  ]
}
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
# Domain ownership: Google maps a domain to Cloud Run only for an account that verified it in
# Webmaster Central. studioface.app IS verified for the gcloud account (gcloud domains
# list-user-verified, 17 Sep 2026). Doing the verification in Terraform needs the
# siteverification OAuth scope, which gcloud user tokens do not carry (ACCESS_TOKEN_SCOPE_INSUFFICIENT),
# so it stays a one-time `gcloud domains verify <domain>` per new domain, not a resource here.
# The same service also serves the static frontend at the apex (one container, one deploy).
resource "google_cloud_run_domain_mapping" "web" {
  name     = var.domain
  location = var.region
  metadata {
    namespace = var.project_id
  }
  spec {
    route_name     = google_cloud_run_v2_service.api.name
    force_override = true
  }
  depends_on = [cloudflare_dns_record.apex_a, cloudflare_dns_record.apex_aaaa]
}

resource "google_cloud_run_domain_mapping" "api" {
  name     = "api.${var.domain}"
  location = var.region
  metadata {
    namespace = var.project_id
  }
  spec {
    route_name = google_cloud_run_v2_service.api.name
    # A failed first attempt leaves a dead mapping that the backend deletes asynchronously;
    # the replacement then hits "already mapped". The mapping is ours, so override is safe.
    force_override = true
  }
  depends_on = [cloudflare_dns_record.api]
}

# ---------------------------------------------------------------- money guard: budget -> Pub/Sub -> API kill switch
resource "google_pubsub_topic" "budget" {
  name = "budget-alerts"
}
data "google_project" "this" {
  project_id = var.project_id
}

resource "google_billing_budget" "cap" {
  billing_account = var.billing_account
  display_name    = "studioface-monthly-cap"
  budget_filter {
    projects = ["projects/${data.google_project.this.number}"] # API stores the number; the id would re-diff every apply
  }
  amount {
    specified_amount {
      currency_code = "EUR"
      units         = tostring(var.monthly_budget_eur)
    }
  }
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  all_updates_rule {
    pubsub_topic                   = google_pubsub_topic.budget.id
    schema_version                 = "1.0"
    disable_default_iam_recipients = false
  }
  depends_on = [google_project_service.svc]
}
resource "google_pubsub_subscription" "budget_push" {
  name  = "budget-to-api"
  topic = google_pubsub_topic.budget.id
  push_config {
    push_endpoint = "https://api.${var.domain}/internal/budget"
    oidc_token {
      service_account_email = google_service_account.api.email
      # Stated rather than defaulted: the app checks the `aud` claim against exactly this
      # string, and a default that changes shape would fail closed with no obvious cause.
      audience = "https://api.${var.domain}/internal/budget"
    }
  }
}
