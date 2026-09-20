output "stripe_price_eur" { value = stripe_price.eur.id }
# Needed to create a throwaway 0,50 € price against the same product for a live test
# purchase without touching the real one (MORNING-REPORT.md).
output "stripe_product_id" { value = stripe_product.headshots.id }
output "stripe_price_usd" { value = stripe_price.usd.id }
output "stripe_webhook_secret" {
  value     = stripe_webhook_endpoint.api.secret
  sensitive = true
}
output "cloud_run_url" { value = google_cloud_run_v2_service.api.uri }
output "wif_provider" { value = google_iam_workload_identity_pool_provider.gh.name }
output "deployer_sa" { value = google_service_account.deployer.email }
output "github_repo_ssh" { value = github_repository.repo.ssh_clone_url }
output "turnstile_sitekey" { value = cloudflare_turnstile_widget.preview.id }
output "turnstile_secret" {
  value     = cloudflare_turnstile_widget.preview.secret
  sensitive = true
}
output "github_repo_https" { value = github_repository.repo.http_clone_url }
