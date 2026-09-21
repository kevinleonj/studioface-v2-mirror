import type { Metadata } from "next";
import { AdLanding } from "@/components/ad-landing";
import { AD_PAGES } from "@/content/ad-pages";
import { SITE_URL } from "@/lib/config";

/**
 * Google Ads landing page for the "foto curriculum" / "foto cv" keyword group
 * (Keyword Planner, Kevin's account, Spain, Spanish, 20 September 2026; 1K-10K
 * searches/month). Task 23 — no code here is specific to this audience except the
 * <head> metadata below and the CONTENT passed to AdLanding; the page itself is the
 * shared component in frontend/src/components/ad-landing.tsx.
 */

const CONTENT = AD_PAGES["foto-cv"];
const SHARE_IMAGE = `${SITE_URL}/share.jpg`;

export const metadata: Metadata = {
  title: CONTENT.title,
  description: CONTENT.description,
  // metadataBase (root layout) resolves this to https://studioface.app/foto-cv/.
  alternates: { canonical: "/foto-cv/" },
  openGraph: {
    title: CONTENT.title,
    description: CONTENT.description,
    url: "/foto-cv/",
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

export default function FotoCvPage() {
  return <AdLanding content={CONTENT} />;
}
