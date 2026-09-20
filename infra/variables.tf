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
