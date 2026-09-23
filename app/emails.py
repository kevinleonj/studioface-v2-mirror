"""What the customer actually receives. Pure functions: no network, no secrets.

The delivery email was the bare URL and nothing else — `text=body`, where body was the
gallery link. That is the single worst-looking email a business can send. A naked link
with no sender identity, no context and no plain-text alternative is what phishing
looks like to a person and what bulk looks like to a spam filter, and it arrives at the
exact moment the customer is deciding whether they were right to pay us.

Every message here ships BOTH html and text. Gmail and Outlook both weigh a missing
plain-text part, and some corporate clients render nothing else.

Styling is inline and table-free-ish on purpose: Gmail strips <style> blocks, so
anything that matters is an inline attribute. Colours are direction B from
docs/DESIGN.md, so the email and the site look like the same company.

The trader identity in the footer is a legal requirement, not decoration: LSSI-CE
Art. 10 for commercial communications, and it is the same identity as /legal.
"""

from __future__ import annotations

from dataclasses import dataclass

PAPER = "#F2F1ED"
INK = "#141312"
DIM = "#5C5851"
ACCENT = "#C3352B"

TRADER = "Kevin Daniel León Jouvin, NIF Z3714124-C, Calle de Diego de León 13, 7º A, 28006 Madrid"
SUPPORT = "hola@studioface.app"
SITE = "https://studioface.app"

REFUND_SENTINEL = "REFUND"
# Mirrors app/core.py's OWNER_ALERT_PREFIX exactly — kept as a second constant, not a
# shared import, same reasoning as REFUND_SENTINEL above: this module ships no
# dependency on core. tests/test_credit_exhausted.py pins the two strings equal.
OWNER_ALERT_PREFIX = "OWNER_ALERT:"
# Task 42's two alerts, mirroring app/core.py's DAILY_CEILING_ALERT_PREFIX and
# REFUND_ALARM_PREFIX exactly, same reasoning and same held-out equality test.
DAILY_CEILING_ALERT_PREFIX = "OWNER_ALERT_CEILING:"
REFUND_ALARM_PREFIX = "OWNER_ALERT_REFUNDS:"
# Task 71's new alert, mirroring app/core.py's DAILY_PREVIEW_CAP_ALERT_PREFIX exactly,
# same reasoning and same held-out equality test.
DAILY_PREVIEW_CAP_ALERT_PREFIX = "OWNER_ALERT_PREVIEW_CAP:"


@dataclass(frozen=True)
class Email:
    subject: str
    html: str
    text: str


def _shell(heading: str, body_html: str) -> str:
    """One column, 600px, centred. Inline styles only — Gmail drops <style>."""
    return (
        f'<div style="margin:0;padding:24px 0;background:{PAPER};'
        f'font-family:Helvetica,Arial,sans-serif;color:{INK}">'
        f'<div style="max-width:600px;margin:0 auto;padding:0 24px">'
        # The wordmark is the name. This was 11px, letter-spacing .2em, ALL CAPS: skill
        # cluster 5, the same device as the .sf-label that was deleted from the page.
        # It survived both rounds because scripts/design_audit.py reads frontend/out and
        # this is Python — the audit has never been able to see the one thing the
        # customer actually receives. tests/test_emails.py can.
        f'<p style="margin:0 0 24px;font-size:16px;color:{INK}">StudioFace</p>'
        f'<h1 style="margin:0 0 16px;font-size:24px;line-height:1.2;font-weight:600">{heading}</h1>'
        f"{body_html}"
        f'<hr style="border:0;border-top:1px solid {INK};margin:32px 0 16px">'
        f'<p style="margin:0 0 4px;font-size:12px;color:{DIM}">'
        f"Las imágenes se generan con inteligencia artificial a partir de las fotos que subes."
        f"</p>"
        f'<p style="margin:0 0 4px;font-size:12px;color:{DIM}">{TRADER}</p>'
        f'<p style="margin:0;font-size:12px;color:{DIM}">'
        f'¿Alguna duda? Responde a este correo o escribe a <a href="mailto:{SUPPORT}" '
        f'style="color:{INK}">{SUPPORT}</a>.</p>'
        f"</div></div>"
    )


def _button(href: str, label: str) -> str:
    return (
        f'<p style="margin:0 0 24px"><a href="{href}" '
        f'style="display:inline-block;background:{ACCENT};color:{PAPER};text-decoration:none;'
        f'font-weight:bold;font-size:16px;padding:14px 28px">{label}</a></p>'
    )


def delivery(link: str) -> Email:
    """The one that matters. It arrives when the customer is deciding whether paying
    us was a good idea."""
    body = (
        '<p style="margin:0 0 24px;font-size:16px;line-height:1.5">'
        "Tus cuatro fotos ya están listas. Ábrelas y descárgalas desde este enlace privado:"
        "</p>"
        + _button(link, "Ver mis fotos")
        + f'<p style="margin:0 0 8px;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Si el botón no funciona, copia esta dirección en tu navegador:<br>"
        f'<a href="{link}" style="color:{INK};word-break:break-all">{link}</a></p>'
        + f'<p style="margin:0 0 8px;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Los enlaces de descarga caducan a los 15 minutos. Vuelve a abrir esta página "
        f"cuando quieras y se renuevan solos.</p>"
        + f'<p style="margin:0;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Guardamos tus cuatro fotos un año. Las fotos que subiste se borran a los 7 días.</p>"
    )
    text = (
        "Tus cuatro fotos de StudioFace ya están listas.\n\n"
        f"Ábrelas aquí: {link}\n\n"
        "Los enlaces de descarga caducan a los 15 minutos; vuelve a abrir la página y se "
        "renuevan solos.\n"
        "Guardamos tus cuatro fotos un año. Las fotos que subiste se borran a los 7 días.\n"
        "Las imágenes se generan con inteligencia artificial a partir de las fotos que subes.\n\n"
        f"{TRADER}\n¿Alguna duda? Escribe a {SUPPORT}\n{SITE}\n"
    )
    return Email(
        "Tus fotos de StudioFace ya están listas", _shell("Tus fotos están listas", body), text
    )


def refund() -> Email:
    """Sent when generation could not produce four images. It says what happened and
    what we did, because the customer's money moved and nobody likes finding that out
    from a bank statement."""
    body = (
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5">'
        f"No hemos conseguido generar tus cuatro fotos, así que hemos cancelado el pedido "
        f"y te devolvemos el importe completo. No tienes que hacer nada.</p>"
        f'<p style="margin:0 0 16px;font-size:14px;line-height:1.5;color:{DIM}">'
        f"La devolución tarda unos días en aparecer en tu banco, según el método de pago "
        f"que usaste.</p>"
        f'<p style="margin:0 0 24px;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Las fotos que subiste se borran a los 7 días, como siempre.</p>"
        + _button(SITE, "Volver a intentarlo")
    )
    text = (
        "No hemos conseguido generar tus cuatro fotos.\n\n"
        "Hemos cancelado el pedido y te devolvemos el importe completo. No tienes que hacer "
        "nada. La devolución tarda unos días en aparecer en tu banco.\n\n"
        "Las fotos que subiste se borran a los 7 días.\n\n"
        f"Si quieres volver a intentarlo: {SITE}\n\n"
        f"{TRADER}\n¿Alguna duda? Escribe a {SUPPORT}\n"
    )
    return Email(
        "Hemos cancelado tu pedido y te devolvemos el importe",
        _shell("Te devolvemos el importe", body),
        text,
    )


def owner_alert(refunded: int) -> Email:
    """Sent to OWNER_ALERT_EMAIL, once, the moment Pipeline._handle_credit_exhausted
    switches the kill switch from off to on. Kevin, not a customer, so plain English
    and no legal footer — but the same `_shell`/`_button` this module already uses
    for everything else, per the task: through the same code that sends the delivery
    and cancellation emails today."""
    order_word = "order" if refunded == 1 else "orders"
    body = (
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5">'
        f"fal has locked the account for lack of credit. {refunded} paid {order_word} "
        f"{'has' if refunded == 1 else 'have'} been refunded automatically and the "
        f"shop has stopped selling — no further orders are taken until you reset the "
        f"kill switch.</p>"
        f'<p style="margin:0;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Add credit at fal.ai/dashboard/billing, then reset config/killswitch in "
        f"Firestore. This is the only email you get for this incident.</p>"
    )
    text = (
        f"fal has locked the account for lack of credit. {refunded} paid {order_word} "
        f"{'has' if refunded == 1 else 'have'} been refunded automatically and the "
        "shop has stopped selling — no further orders are taken until you reset the "
        "kill switch.\n\n"
        "Add credit at fal.ai/dashboard/billing, then reset config/killswitch in "
        "Firestore. This is the only email you get for this incident.\n"
    )
    return Email(
        "StudioFace has stopped selling: fal credit ran out",
        _shell("fal credit ran out", body),
        text,
    )


def daily_ceiling_alert(limit: int) -> Email:
    """Sent to OWNER_ALERT_EMAIL, once, the moment Pipeline.admit refuses an order
    for landing above `limit` paid orders in one UTC day. Task 42, same shell as
    owner_alert above — plain English, no legal footer, Kevin rather than a
    customer."""
    body = (
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5">'
        f"StudioFace has taken {limit} paid orders today, the daily ceiling. The order "
        f"that went over it has been refunded automatically and the shop has stopped "
        f"selling — no further orders are taken until you reset the kill switch.</p>"
        f'<p style="margin:0;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Raise the ceiling in app/guards.py (DailyOrderCeiling) if {limit} a day is "
        f"genuinely too low, then reset config/killswitch in Firestore. This is the "
        f"only email you get for this incident.</p>"
    )
    text = (
        f"StudioFace has taken {limit} paid orders today, the daily ceiling. The order "
        f"that went over it has been refunded automatically and the shop has stopped "
        "selling — no further orders are taken until you reset the kill switch.\n\n"
        f"Raise the ceiling in app/guards.py (DailyOrderCeiling) if {limit} a day is "
        "genuinely too low, then reset config/killswitch in Firestore. This is the "
        "only email you get for this incident.\n"
    )
    return Email(
        f"StudioFace has stopped selling: {limit} paid orders today",
        _shell("Daily order ceiling reached", body),
        text,
    )


def refund_alarm(entries: list[tuple[str, str]]) -> Email:
    """Sent to OWNER_ALERT_EMAIL, once per UTC day, the moment the day's refund
    count first reaches REFUND_ALARM_THRESHOLD — whatever each order's reason.
    Does NOT say the shop has stopped: unlike the two alerts above, this one never
    touches the kill switch, because three refunds in a day is worth a look, not
    proof anything is broken. Task 42."""
    rows = "".join(f'<li style="margin:0 0 4px">{oid} — {reason}</li>' for oid, reason in entries)
    lines = "\n".join(f"{oid} — {reason}" for oid, reason in entries)
    body = (
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5">'
        f"{len(entries)} orders were refunded today. The shop is still selling — this "
        f"is worth a look, not an outage.</p>"
        f'<ul style="margin:0 0 16px;padding-left:20px;font-size:14px;line-height:1.6">'
        f"{rows}</ul>"
        f'<p style="margin:0;font-size:14px;line-height:1.5;color:{DIM}">'
        f"This is the only email you get for today's refunds.</p>"
    )
    text = (
        f"{len(entries)} orders were refunded today. The shop is still selling — this "
        f"is worth a look, not an outage.\n\n{lines}\n\n"
        "This is the only email you get for today's refunds.\n"
    )
    return Email(
        f"StudioFace: {len(entries)} refunds today",
        _shell("Refunds today", body),
        text,
    )


def daily_preview_cap_alert(limit: int) -> Email:
    """Sent to OWNER_ALERT_EMAIL, once per UTC day, the moment RateLimiter.check
    refuses a free preview for `daily_global` (app/guards.py). Task 71, same shell
    as daily_ceiling_alert above — plain English, no legal footer, Kevin rather than
    a customer. Never says the shop has stopped: a preview costs nothing, so unlike
    the paid-order ceiling this never touches the kill switch and the shop keeps
    selling — it is the ad spend, not the shop, that needs pausing."""
    body = (
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5">'
        f"StudioFace has served {limit} free previews today, the daily ceiling. "
        f"Visitors past it can still buy — their photos are stored and the buy "
        f"button still works — but no more free previews run until tomorrow (UTC). "
        f"If this is paid traffic, now is a good time to pause the ads.</p>"
        f'<p style="margin:0;font-size:14px;line-height:1.5;color:{DIM}">'
        f"Raise the ceiling in app/guards.py (RateLimiter.daily_global) if {limit} a "
        f"day is genuinely too low. This is the only email you get for today's cap.</p>"
    )
    text = (
        f"StudioFace has served {limit} free previews today, the daily ceiling. "
        "Visitors past it can still buy — their photos are stored and the buy "
        "button still works — but no more free previews run until tomorrow (UTC). "
        "If this is paid traffic, now is a good time to pause the ads.\n\n"
        f"Raise the ceiling in app/guards.py (RateLimiter.daily_global) if {limit} a "
        "day is genuinely too low. This is the only email you get for today's cap.\n"
    )
    return Email(
        f"StudioFace: {limit} free previews today, the daily cap",
        _shell("Daily preview cap reached", body),
        text,
    )


def for_body(body: str) -> Email:
    """The pipeline's send_email port passes a gallery link, the literal "REFUND",
    "OWNER_ALERT:<n>", "OWNER_ALERT_CEILING:<n>", "OWNER_ALERT_PREVIEW_CAP:<n>" or
    "OWNER_ALERT_REFUNDS:<id:reason,...>". Sniffing a sentinel out of a message body
    is a poor contract and it is called out in HANDOFF as a follow-up; it is
    preserved here so this change stays confined to what the customer (or, for the
    alert cases, Kevin) sees."""
    if body == REFUND_SENTINEL:
        return refund()
    if body.startswith(DAILY_CEILING_ALERT_PREFIX):
        return daily_ceiling_alert(int(body.removeprefix(DAILY_CEILING_ALERT_PREFIX)))
    if body.startswith(DAILY_PREVIEW_CAP_ALERT_PREFIX):
        return daily_preview_cap_alert(int(body.removeprefix(DAILY_PREVIEW_CAP_ALERT_PREFIX)))
    if body.startswith(REFUND_ALARM_PREFIX):
        pairs = body.removeprefix(REFUND_ALARM_PREFIX).split(",")
        entries = [tuple(pair.split(":", 1)) for pair in pairs if pair]
        return refund_alarm(entries)
    if body.startswith(OWNER_ALERT_PREFIX):
        return owner_alert(int(body.removeprefix(OWNER_ALERT_PREFIX)))
    return delivery(body)
