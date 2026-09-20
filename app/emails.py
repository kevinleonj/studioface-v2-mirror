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

TRADER = "limeralda, NIF Z3714124-C, Maria de Molina 31, Madrid"
SUPPORT = "hola@studioface.app"
SITE = "https://studioface.app"

REFUND_SENTINEL = "REFUND"


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


def for_body(body: str) -> Email:
    """The pipeline's send_email port passes either a gallery link or the literal
    "REFUND". Sniffing a sentinel out of a message body is a poor contract and it is
    called out in HANDOFF as a follow-up; it is preserved here so this change stays
    confined to what the customer sees."""
    return refund() if body == REFUND_SENTINEL else delivery(body)
