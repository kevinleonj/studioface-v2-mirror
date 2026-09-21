import type { Metadata } from "next";
import { AdLanding } from "@/components/ad-landing";
import { AD_PAGES } from "@/content/ad-pages";
import { SITE_URL } from "@/lib/config";

/**
 * Google Ads landing page for the "foto linkedin" keyword group (Keyword Planner,
 * Kevin's account, Spain, Spanish, 20 September 2026). Task 23 — see
 * frontend/src/app/foto-cv/page.tsx for the sibling page; both are thin route files
 * over the one shared component, frontend/src/components/ad-landing.tsx.
 */

const CONTENT = AD_PAGES["foto-linkedin"];
const SHARE_IMAGE = `${SITE_URL}/share.jpg`;

export const metadata: Metadata = {
  title: CONTENT.title,
  description: CONTENT.description,
  // metadataBase (root layout) resolves this to https://studioface.app/foto-linkedin/.
  alternates: { canonical: "/foto-linkedin/" },
  openGraph: {
    title: CONTENT.title,
    description: CONTENT.description,
    url: "/foto-linkedin/",
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
    title: CONTENT.title,
    description: CONTENT.description,
    images: [SHARE_IMAGE],
  },
};

export default function FotoLinkedinPage() {
  return <AdLanding content={CONTENT} />;
}
