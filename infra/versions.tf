terraform {
  required_version = ">= 1.9"
  required_providers {
    google     = { source = "hashicorp/google", version = "~> 7.0" }
    stripe     = { source = "lukasaron/stripe", version = "~> 3.4" }
    github     = { source = "integrations/github", version = "~> 6.0" }
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.0" }
  }
  backend "gcs" {}
}
