provider "google" {
  project = var.project_id
  region  = var.region
  # Credentials come from gcloud (GOOGLE_OAUTH_ACCESS_TOKEN). gcloud user credentials belong to a
  # Google-owned project, so quota-project-required APIs (billingbudgets) need an explicit quota
  # project: user_project_override + billing_project (provider_reference, "Quota Management").
  user_project_override = true
  billing_project       = var.project_id
}
provider "stripe" {}                           # STRIPE_API_KEY from env (bootstrap exports it)
provider "github" { owner = var.github_owner } # GITHUB_TOKEN from env (gh auth token)
provider "cloudflare" {}                       # CLOUDFLARE_API_TOKEN from env
