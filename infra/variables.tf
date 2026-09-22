variable "project_id" { type = string }
variable "billing_account" { type = string }
variable "github_owner" { type = string }
variable "cloudflare_zone_id" { type = string }
variable "region" {
  type    = string
  default = "europe-west1" # domain mapping + Firebase Hosting rewrites supported here
}
variable "repo_name" {
  type    = string
  default = "studioface-v2"
}
variable "domain" {
  type    = string
  default = "studioface.app"
}
variable "price_eur_cents" {
  type    = number
  default = 1999
}
variable "price_usd_cents" {
  type    = number
  default = 999
}
variable "monthly_budget_eur" {
  type    = number
  default = 40
}
variable "cloudflare_account_id" { type = string }
# GA4 Measurement ID (G-XXXXXXXXXX). Not a secret — it ships in the page as well.
# Empty is valid: the Measurement Protocol backstop then skips the purchase event.
variable "ga4_measurement_id" {
  type    = string
  default = ""
}
# Where Pipeline._handle_credit_exhausted sends the one alert when fal locks the
# account for lack of credit. A plain address, never a secret (task 41). Empty is
# valid: app/config.py then leaves owner_alert_email unset and the alert is skipped,
# never the refund or the kill switch.
variable "owner_alert_email" {
  type    = string
  default = ""
}
