"use client";

/**
 * Task 23. The ONE shared component both Google Ads landing pages render through.
 *
 * /foto-cv/ and /foto-linkedin/ (frontend/src/app/foto-cv/page.tsx and
 * frontend/src/app/foto-linkedin/page.tsx) are thin route files: each sets its own
 * <head> metadata from content/ad-pages.ts and renders <AdLanding content={...} />.
 * Nothing about the slider, the first-screen button, the uploader or the price block
 * is duplicated between the two pages — they are the same elements (Comparador,
 * FoldCta, UploadForm) called once each, from here.
 *
 * This is NOT the home page (frontend/src/app/page.tsx) reused: the brief keeps the
 * home page's first-screen layout untouched, so this component is new rather than a
 * refactor of Home into something Home also calls. What the two share — the grid
 * shape, the price block sentence that carries the AI-disclosure, the uploader wiring
 * — is the same because both were built to the same design (docs/DESIGN.md), not
 * because one imports the other.
 */

import Script from "next/script";
import { Faq } from "@/components/faq";
import { FoldCta, UPLOADER_ID } from "@/components/fold-cta";
import { Comparador } from "@/components/comparador";
import { UploadForm } from "@/components/upload-form";
import type { AdPageContent } from "@/content/ad-pages";
import { PRICE_EUR, PRICE_LABEL, SITE_URL, TURNSTILE_SITEKEY } from "@/lib/config";

// Same shape as the home page's PRODUCT_LD/ORGANIZATION_LD (page.tsx), built once here
// so the two ad pages get identical structured data wiring rather than two copies of
// the object literal.
function productLd(content: AdPageContent) {
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: content.title,
    description: content.description,
    image: `${SITE_URL}/share.jpg`,
    brand: { "@type": "Brand", name: "StudioFace" },
    offers: {
      "@type": "Offer",
      url: `${SITE_URL}/${content.slug}/`,
      priceCurrency: "EUR",
      price: PRICE_EUR.toFixed(2),
      availability: "https://schema.org/InStock",
    },
  };
}

const ORGANIZATION_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "StudioFace",
  url: SITE_URL,
};

export function AdLanding({ content }: { content: AdPageContent }) {
  return (
    <>
      {TURNSTILE_SITEKEY ? (
        <Script
          src="https://challenges.cloudflare.com/turnstile/v0/api.js"
          strategy="afterInteractive"
        />
      ) : null}

      <section className="sf-wrap pt-2 sm:pt-12">
        {/* Same grid shape as the home hero (page.tsx): the picture follows the H1 on a
            phone and sits beside it on a desktop, so the proof-before-price hypothesis
            (docs/CONVERSION.md #1) holds here too. */}
        <div className="grid gap-x-[var(--s4)] gap-y-[var(--s2)] lg:grid-cols-[7fr_5fr] lg:grid-rows-[auto_1fr] lg:items-start lg:gap-y-[var(--s3)]">
          <h1 className="sf-h1 font-[family-name:var(--font-newsreader)] lg:col-start-1 lg:row-start-1">
            {content.h1}
          </h1>

          <div className="lg:col-start-2 lg:row-start-1 lg:row-span-2">
            <Comparador />
            <FoldCta />
          </div>

          <div className="lg:col-start-1 lg:row-start-2">
            <p data-subhead className="max-w-[52ch] text-[color:var(--muted-foreground)]">
              {content.intro}
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

        <p className="mt-[var(--s2)] text-sm">
          <a
            data-recover-under-uploader
            href="/recuperar/"
            className="sf-focus inline-flex min-h-[44px] items-center text-[color:var(--muted-foreground)] underline decoration-[color:var(--primary)] underline-offset-4 [text-decoration-skip-ink:none]"
          >
            ¿Ya has comprado? Recuperar mis fotos
          </a>
        </p>
      </section>

      <section className="sf-wrap mt-[var(--s5)]">
        <h2 className="font-[family-name:var(--font-newsreader)] text-2xl">Preguntas frecuentes</h2>
        <Faq only={content.faqQuestions} />
      </section>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(productLd(content)) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_LD) }}
      />
    </>
  );
}
