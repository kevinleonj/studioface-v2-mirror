/**
 * Task 23. The ONE content file for the two Google Ads landing pages.
 *
 * Keyword Planner (Kevin's account, Spain, Spanish, 20 September 2026): demand splits
 * into two exact-phrase groups, "foto curriculum"/"foto cv" (1K-10K searches/month) and
 * "foto linkedin". Each group gets its own page so the ad and the landing page use the
 * same words the visitor typed, which is what Quality Score and the visitor both reward.
 *
 * Every page built from this file renders through the ONE shared component,
 * components/ad-landing.tsx — no markup is copied between /foto-cv/ and /foto-linkedin/.
 *
 * Copy rules (docs/DESIGN.md, studioface-ui skill): es-ES, tú form, "19,99 €", no
 * exclamation marks, no superlatives. Every AI-generated image is disclosed in visible
 * copy — the shared component's price block already carries that sentence, so it is not
 * repeated here.
 */

export type AdPageSlug = "foto-cv" | "foto-linkedin";

export type AdPageContent = {
  slug: AdPageSlug;
  h1: string;
  title: string;
  /** Under 155 characters. Must say "prueba gratis, sin registro" and "19,99 €". */
  description: string;
  /** 60-90 words, written for this reader. */
  intro: string;
  /** The three FAQ questions this page shows, in the order shown — identical text to
   *  components/faq.tsx so there is one source of truth for the answer, not two. */
  faqQuestions: readonly [string, string, string];
};

// Same three questions on both pages ("three matching questions from the FAQ", brief):
// the identity objection that stops anyone from paying, what the money buys, and the
// one real refund condition — the three a visitor arriving from a search ad needs
// before they will hand over four selfies to a page they have never seen before.
const SHARED_FAQ: readonly [string, string, string] = [
  "¿Me voy a parecer a mí?",
  "¿Qué recibo por 19,99 €?",
  "¿Cuándo devolvéis el dinero?",
];

export const AD_PAGES: Record<AdPageSlug, AdPageContent> = {
  "foto-cv": {
    slug: "foto-cv",
    h1: "Tu foto para el currículum, en dos minutos",
    title: "Foto de currículum profesional con IA | StudioFace",
    description:
      "Sube tus selfies y prueba gratis, sin registro. Foto de currículum profesional " +
      "con IA por 19,99 €, IVA incluido.",
    intro:
      "Una foto de currículum profesional influye en si te llaman para la entrevista. " +
      "Sube entre una y cuatro selfies tuyas, de frente, y en unos minutos recibes una " +
      "prueba gratis, sin registro ni tarjeta, generada con inteligencia artificial a " +
      "partir de tus propias fotos. Si te convence, pagas una vez y recibes cuatro " +
      "retratos distintos en alta resolución, listos para tu currículum, tu perfil de " +
      "empleo o tu web personal. Trabajamos sobre tu cara real: cambiamos la luz, el " +
      "fondo y la ropa, no tus rasgos.",
    faqQuestions: SHARED_FAQ,
  },
  "foto-linkedin": {
    slug: "foto-linkedin",
    h1: "Tu foto profesional para LinkedIn, en dos minutos",
    title: "Foto profesional para LinkedIn con IA | StudioFace",
    description:
      "Sube tus selfies y prueba gratis, sin registro. Foto profesional para LinkedIn " +
      "con IA por 19,99 €, IVA incluido.",
    intro:
      "Tu foto de perfil de LinkedIn es lo primero que ve un reclutador o un cliente " +
      "antes de leer una sola línea. Sube entre una y cuatro selfies tuyas, de frente, " +
      "y recibe en unos minutos una prueba gratis, sin registro ni tarjeta, generada " +
      "con inteligencia artificial a partir de tus propias fotos. Si te convence, " +
      "pagas una vez y recibes cuatro retratos profesionales distintos en alta " +
      "resolución, listos para subir a tu perfil. Trabajamos sobre tu cara real: " +
      "cambiamos la luz, el fondo y la ropa, nunca tus rasgos.",
    faqQuestions: SHARED_FAQ,
  },
};
