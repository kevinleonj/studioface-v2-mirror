"use client";

/**
 * The FAQ, and the one question that was missing from it.
 *
 * "¿Me voy a parecer a mí?" is the objection this product exists under — a stranger is
 * being asked for four photographs of their face on the promise that what comes back is
 * still them. It was answered nowhere: not in the FAQ, and only obliquely in the
 * subheading. docs/CONVERSION.md H2.
 *
 * <details>, not a JS accordion: it opens without JavaScript, it is keyboard operable
 * for free, the answers are in the DOM for a crawler either way, and the `toggle` event
 * is the honest place to measure whether the short answer above did its job. A high
 * open rate on the identity question means the reassurance is not landing.
 *
 * The identity one is first because it is the one that stops people paying.
 */

import { EVENTS, track } from "@/lib/track";
import { PRICE_LABEL } from "@/lib/config";

export const IDENTITY_Q = "¿Me voy a parecer a mí?";

// Exported (task 23) so the ad landing pages can pick a matching subset of THESE SAME
// question/answer pairs, rather than a second copy of the copy — one source of truth
// for what each question answers, wherever it is shown.
export const FAQ = [
  {
    q: IDENTITY_Q,
    a:
      "Sí. Trabajamos sobre tus propias fotos: cambiamos la luz, el fondo y la ropa, no tu " +
      "cara. No adelgazamos, no rejuvenecemos y no retocamos rasgos. Si el resultado no se " +
      "parece a ti, lo verás en la prueba gratuita antes de pagar nada.",
  },
  {
    q: `¿Qué recibo por ${PRICE_LABEL}?`,
    a: "Cuatro fotos distintas en alta resolución, listas para descargar.",
  },
  {
    q: "¿Cuánto tarda?",
    a: "Unos minutos. Te avisamos por correo con un enlace privado.",
  },
  {
    q: "¿Qué pasa con mis fotos?",
    a: "Las que subes se borran a los 7 días. Los retratos quedan un año.",
  },
  {
    // This used to ask "¿Y si no me convencen?" — a satisfaction guarantee — and answer
    // with our delivery condition. The code refunds in exactly one case: fewer than four
    // images generated (core.Pipeline.run, min_deliverable=4).
    q: "¿Cuándo devolvéis el dinero?",
    a:
      "En un caso: si no conseguimos generar las cuatro fotos, te devolvemos el importe " +
      "automáticamente, sin que tengas que pedirlo. No devolvemos el importe porque el " +
      "resultado no te guste. Para eso tienes una previsualización gratis antes de pagar.",
  },
];

// `only`: an ad landing page shows three questions, not all five (task 23). Filtering
// here, rather than each caller re-typing a `.filter()`, keeps the ordering rule (the
// identity objection first, docs/CONVERSION.md H2) in exactly one place.
export function Faq({ only }: { only?: readonly string[] }) {
  const items = only ? FAQ.filter((item) => only.includes(item.q)) : FAQ;
  return (
    <div className="mt-[var(--s3)] grid gap-0 sm:grid-cols-2 sm:gap-x-[var(--s4)]">
      {items.map((item) => (
        <details
          key={item.q}
          className="border-b border-[color:var(--border)] py-[var(--s2)]"
          onToggle={(e) => {
            if (item.q === IDENTITY_Q && e.currentTarget.open) track(EVENTS.faqIdentityOpen);
          }}
        >
          <summary className="sf-focus flex min-h-[44px] cursor-pointer items-center font-[family-name:var(--font-newsreader)] text-xl">
            {item.q}
          </summary>
          {/* sf-answer: moment 5. */}
          <p className="sf-answer mt-[var(--s1)] max-w-[60ch] text-[color:var(--muted-foreground)]">
            {item.a}
          </p>
        </details>
      ))}
    </div>
  );
}
