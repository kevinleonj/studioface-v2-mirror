import type { Metadata } from "next";
import Script from "next/script";
import { Faq } from "@/components/faq";
import { Comparador } from "@/components/comparador";
import { FoldCta, UPLOADER_ID } from "@/components/fold-cta";
import { MoreMuestras } from "@/components/more-muestras";
import { UploadForm } from "@/components/upload-form";
import { PRICE_EUR, PRICE_LABEL, SITE_URL, TURNSTILE_SITEKEY } from "@/lib/config";

/**
 * Landing page — direction B, "Hoja de contactos" (docs/DESIGN.md).
 *
 * Unchanged constraints, all load-bearing for the Google Ads account: the H1
 * contains "foto de perfil profesional", the price sits above the fold, and the
 * LCP element is the H1 — so there is still no hero image.
 *
 * What changed, and why, from the critique in docs/design-review/2026-09-17-2015:
 *  - The card is gone. A contact sheet is a printed object; the upload sits inside
 *    a ruled frame, not on a floating surface. No shadows anywhere on the page.
 *  - "Cómo funciona" was three equal columns — the cardocalypse geometry, which is
 *    banned even without card chrome. It is now a numbered sheet with an asymmetric
 *    2fr/1fr/1fr split, carried over from direction C.
 *  - The sample frames sit BELOW the trust facts on mobile, so they stop competing
 *    with the call to action for the same thumb.
 */

const STEPS = [
  { title: "Sube tus selfies", body: "De una a cuatro fotos tuyas, tomadas de frente." },
  { title: "Mira la prueba", body: "Generamos una foto de muestra sin coste ni registro." },
  { title: "Recibe las cuatro", body: "Te llegan por correo en unos minutos." },
];

// Unit page-head. TITLE and DESCRIPTION feed both <head> metadata and the JSON-LD
// below, so the three surfaces (tab title, share card, structured data) never drift
// apart into three different descriptions of the same product.
const TITLE = "Foto de perfil profesional con IA para LinkedIn y CV | StudioFace";
// 119 characters: under the 155 SERP truncation point, names the price and the free
// preview (docs/CONVERSION.md — the proof-before-price hypothesis, restated for a
// search snippet instead of the fold).
const DESCRIPTION =
  "Sube tus selfies y prueba gratis antes de pagar. Recibe tu foto de perfil " +
  "profesional con IA por 19,99 €, IVA incluido.";
const SHARE_IMAGE = `${SITE_URL}/share.jpg`;

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  // metadataBase (root layout) resolves this to https://studioface.app/.
  alternates: { canonical: "/" },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "/",
    siteName: "StudioFace",
    locale: "es_ES",
    type: "website",
    images: [
      {
        url: SHARE_IMAGE,
        width: 1200,
        height: 630,
        alt: "Antes y después de una foto de perfil generada con StudioFace",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: [SHARE_IMAGE],
  },
};

// Price comes from PRICE_EUR (lib/config.ts), the single existing constant, so the
// structured data can never disagree with what the checkout page actually charges.
// No aggregateRating and no FAQPage here, by the brief: neither claim is backed by a
// real review count or a machine-readable FAQ, and an unbacked one is the kind of rich
// result Google's own spam policies act on.
const PRODUCT_LD = {
  "@context": "https://schema.org",
  "@type": "Product",
  name: TITLE,
  description: DESCRIPTION,
  image: SHARE_IMAGE,
  brand: { "@type": "Brand", name: "StudioFace" },
  offers: {
    "@type": "Offer",
    url: SITE_URL,
    priceCurrency: "EUR",
    price: PRICE_EUR.toFixed(2),
    availability: "https://schema.org/InStock",
  },
};

const ORGANIZATION_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "StudioFace",
  url: SITE_URL,
};

export default function Home() {
  return (
    <>
      {TURNSTILE_SITEKEY ? (
        <Script
          src="https://challenges.cloudflare.com/turnstile/v0/api.js"
          strategy="afterInteractive"
        />
      ) : null}

      <section className="sf-wrap pt-2 sm:pt-12">
        {/* ONE grid, explicitly placed, because the reading order on a phone is not the
            reading order on a desktop.

            Measured at 390x844 with the consent banner up (its 155px is part of every
            first visit): the old order put the first photograph at y=606 inside a 689px
            slot, so a visitor met 606px of prose and then the top of someone's hair.
            docs/CONVERSION.md hypothesis 1 says the proof comes before the price, and it
            did not. The picture now follows the H1 directly on a phone; on a desktop the
            column split puts it back beside the words. */}
        <div className="grid gap-x-[var(--s4)] gap-y-[var(--s2)] lg:grid-cols-[7fr_5fr] lg:grid-rows-[auto_1fr] lg:items-start lg:gap-y-[var(--s3)]">
          {/* U2. The old heading described a process; this one names the place the
              photograph is going, which is what the visitor typed into Google. "en dos
              minutos" stays on measurement, not preference: the free preview has run at
              10.04s and 12.30s and full generation at 14.56s, 19.78s and 28.98s, against
              U2's 120-second threshold.

              The phrase "foto de perfil profesional" leaves the H1, which the UI skill
              asks to keep for Quality Score. It survives in the page title (unit S2),
              where the ad account reads it. Flagged rather than silently dropped. */}
          <h1 className="sf-h1 font-[family-name:var(--font-newsreader)] lg:col-start-1 lg:row-start-1">
            Tu foto profesional para LinkedIn, en dos minutos
          </h1>

          {/* The inset shape, not the even pair: measured, it gives the "después" four
              times the area at both sizes (tests/test_hero.py). The "antes" is the
              disclosure, not the product, and an even split spent half the only
              photograph on the problem. */}
          {/* U5's button lives with the slider, not under the whole grid: "directly under
              the slider" is the same place at every width only if it is in the same
              column. */}
          <div className="lg:col-start-2 lg:row-start-1 lg:row-span-2">
            <Comparador />
            <FoldCta />
          </div>

          <div className="lg:col-start-1 lg:row-start-2">
            <p data-subhead className="max-w-[52ch] text-[color:var(--muted-foreground)]">
              Sube tus selfies y recibe cuatro retratos para LinkedIn, tu CV o tu web, hechos a
              partir de tu cara y de nadie más.
            </p>

            <div className="mt-[var(--s3)]">
              <p className="font-[family-name:var(--font-newsreader)] text-[28px] leading-none">
                {PRICE_LABEL}
              </p>
              <p className="mt-[var(--s1)] text-sm text-[color:var(--muted-foreground)]">
                IVA incluido, pago único
              </p>
              <p className="mt-[var(--s2)] text-sm text-[color:var(--muted-foreground)]">
                Sin registro y sin tarjeta para la prueba. Pagas con tarjeta al final, a través
                de Stripe. Las imágenes finales están generadas con inteligencia artificial a
                partir de tus fotos.
              </p>
            </div>
          </div>
        </div>

        <div
          id={UPLOADER_ID}
          className="mt-[var(--s4)] rounded-[var(--radius)] bg-[color:var(--secondary)] p-[var(--s3)]"
        >
          <p className="mb-[var(--s2)] text-sm text-[color:var(--muted-foreground)]">Empieza aquí</p>
          <UploadForm />
        </div>

        {/* Unit U1. "Recuperar mis fotos" left the mobile header, so it needs a home that
            a person on a phone actually reaches. Directly under the uploader is where
            somebody realises they have bought this before and cannot find the email. */}
        <p className="mt-[var(--s2)] text-sm">
          <a
            data-recover-under-uploader
            href="/recuperar/"
            className="sf-focus inline-flex min-h-[44px] items-center text-[color:var(--muted-foreground)] underline decoration-[color:var(--primary)] underline-offset-4"
          >
            ¿Ya has comprado? Recuperar mis fotos
          </a>
        </p>
      </section>

      <section id="como-funciona" className="sf-wrap mt-[var(--s5)]">
        <h2 className="font-[family-name:var(--font-newsreader)] text-2xl">Cómo funciona</h2>
        {/* 2fr/1fr/1fr, not repeat(3,1fr): three equal columns is the cardocalypse
            geometry, and it is a tell with or without the card. */}
        <ol className="mt-[var(--s3)] grid gap-[var(--s3)] sm:grid-cols-[2fr_1fr_1fr]">
          {STEPS.map((step, i) => (
            <li key={step.title} className="pt-[var(--s2)]">
              <span className="text-sm text-[color:var(--muted-foreground)]">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-[var(--s1)] font-[family-name:var(--font-newsreader)] text-xl">
                {step.title}
              </h3>
              <p className="mt-[var(--s1)] text-[color:var(--muted-foreground)]">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="sf-wrap mt-[var(--s5)]">
        <h2 className="font-[family-name:var(--font-newsreader)] text-2xl">Preguntas frecuentes</h2>
        <Faq />
      </section>

      {/* The remaining pairs. Every one is labelled, in the caption and in the alt
          text, as a generated person run through the real pipeline. Showing a
          generated face as a customer result without saying so is a misleading
          representation of results (Directive 2005/29/EC, Ley 3/1991) and an
          undisclosed AI image (AI Act Art. 50). */}
      <section className="sf-wrap mt-[var(--s5)]">
        <h2 className="font-[family-name:var(--font-newsreader)] text-2xl">Más muestras</h2>
        <MoreMuestras />
      </section>

      {/* Placed last, not first: this is invisible structured data, and putting it
          before the hero moved its serialised price into the raw HTML ahead of the
          real photograph, which broke tests/test_hero.py's proof-before-price check
          on text it never meant to read. Position in the DOM does not affect how a
          crawler reads JSON-LD. */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(PRODUCT_LD) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_LD) }}
      />
    </>
  );
}
