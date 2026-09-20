resource "stripe_product" "headshots" {
  name        = "StudioFace: 4 fotos profesionales"
  description = "4 fotos de perfil profesionales generadas con IA. Entrega en 1 minuto."
}
resource "stripe_price" "eur" {
  product     = stripe_product.headshots.id
  currency    = "eur"
  unit_amount = var.price_eur_cents
  metadata    = { market = "es" }
}
resource "stripe_price" "usd" {
  product     = stripe_product.headshots.id
  currency    = "usd"
  unit_amount = var.price_usd_cents
  metadata    = { market = "ec" }
}
resource "stripe_webhook_endpoint" "api" {
  url            = "https://api.${var.domain}/api/stripe/webhook"
  description    = "StudioFace order webhook"
  # Exactly the set app/main.py dispatches on, and a test compares the two in both
  # directions. refund.updated and refund.failed are GO-LIVE step 11b: Bizum refunds are
  # asynchronous, so Refund.create returns `pending` and these are the only things that
  # ever say whether the money actually moved.
  enabled_events = ["checkout.session.completed", "refund.updated", "refund.failed"]
}
