# DNS-only (grey cloud) on day one: Cloud Run's managed certificate for the domain
# mapping is issued against direct DNS. Switch proxied=true AFTER the mapping shows
# a certificate, to put Cloudflare's free WAF/rate limiting in front. The apex is Firebase Hosting.
resource "cloudflare_dns_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  type    = "CNAME"
  content = "ghs.googlehosted.com"
  proxied = false
  ttl     = 1
}

# Turnstile widget (free). Secret feeds Secret Manager via bootstrap; sitekey goes to the frontend.
resource "cloudflare_turnstile_widget" "preview" {
  account_id = var.cloudflare_account_id
  name       = "studioface-preview"
  domains    = [var.domain, "localhost"]
  mode       = "managed"
}

# Apex records for the Cloud Run mapping of studioface.app. These are Google's published anycast
# addresses for domain mappings (docs.cloud.google.com/run/docs/mapping-custom-domains; the mapping's
# status.resourceRecords returns the same set). DNS-only until the certificate is issued.
locals {
  run_apex_a    = ["216.239.32.21", "216.239.34.21", "216.239.36.21", "216.239.38.21"]
  run_apex_aaaa = ["2001:4860:4802:32::15", "2001:4860:4802:34::15", "2001:4860:4802:36::15", "2001:4860:4802:38::15"]
}
resource "cloudflare_dns_record" "apex_a" {
  for_each = toset(local.run_apex_a)
  zone_id  = var.cloudflare_zone_id
  name     = var.domain
  type     = "A"
  content  = each.value
  proxied  = false
  ttl      = 1
}
resource "cloudflare_dns_record" "apex_aaaa" {
  for_each = toset(local.run_apex_aaaa)
  zone_id  = var.cloudflare_zone_id
  name     = var.domain
  type     = "AAAA"
  content  = each.value
  proxied  = false
  ttl      = 1
}
