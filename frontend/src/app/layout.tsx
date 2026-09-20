import type { Metadata } from "next";
import { Newsreader, Public_Sans } from "next/font/google";
import { Analytics, ConsentBanner, ConsentDefaults } from "@/components/consent";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { SITE_URL } from "@/lib/config";
import "./globals.css";

// docs/DESIGN.md, direction B. TWO families now: Newsreader sets
// headlines and Public Sans sets everything else. Chivo Mono is gone with .sf-label:
// and nothing else. All three SIL OFL 1.1 via Google Fonts. Inter and Fraunces are
// gone: together with cream they were the single P0 the design audit found.
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  display: "swap",
});
const publicSans = Public_Sans({
  variable: "--font-public-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  // Resolves every relative URL in every page's metadata (canonical, og:image) to an
  // absolute https://studioface.app/... address, which is what a crawler needs — a
  // relative og:image is undefined behaviour per the Open Graph protocol.
  metadataBase: new URL(SITE_URL),
  title: "StudioFace — foto de perfil profesional con IA",
  description:
    "Sube tus selfies y recibe cuatro fotos de perfil profesionales en unos minutos. 19,99 € IVA incluido.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es-ES"
      className={`${newsreader.variable} ${publicSans.variable} h-full antialiased`}
    >
      <head>
        <ConsentDefaults />
      </head>
      <body className="flex min-h-full flex-col bg-[color:var(--background)] text-[color:var(--foreground)]">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
        <ConsentBanner />
        <Analytics />
      </body>
    </html>
  );
}
