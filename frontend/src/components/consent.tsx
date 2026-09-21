"use client";

/**
 * Consent Mode v2, Advanced.
 *
 * Advanced means the Google tags load immediately and send cookieless pings before
 * any choice is made, instead of being held back until consent. So the default must
 * be set BEFORE gtag.js runs, which is why ConsentDefaults is beforeInteractive.
 *
 * All four signals are declared: ad_storage, ad_user_data, ad_personalization and
 * analytics_storage. url_passthrough keeps the click id in the URL when cookies are
 * denied, and ads_data_redaction removes ad identifiers from tags in the same case.
 */

import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { GA4_ID } from "@/lib/config";

const STORAGE_KEY = "sf-consent";
const SIGNALS = [
  "ad_storage",
  "ad_user_data",
  "ad_personalization",
  "analytics_storage",
] as const;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

// The gallery's order id and delivery key travel in the page address. Task 31,
// measured from outside 21 Sep 2026: an old-shape link (/g/?o=...&t=...) sent both to
// Google Analytics on load, cookies or no cookies, because the query string was still
// there when gtag.js read the page's address. A fragment (#o=...&t=...) is never sent
// to any server by the browser, so this rewrites the address BEFORE anything else runs
// — it is the very first script in <head>, ahead of ConsentDefaults and every Google
// script, so the leak cannot happen on the first load either.
//
// Every new link (the redirect after payment, the delivery email, the recover-my-photos
// email — app/main.py, app/core.py) already produces the fragment shape; this exists
// only for links already sitting in a customer's inbox in the old shape. It reads and
// writes location only — nothing here is ever logged or printed.
export function GalleryLinkRewrite() {
  return (
    <Script id="sf-gallery-link-rewrite" strategy="beforeInteractive">
      {`(function(){
var l=window.location;
if(l.pathname!=='/g/'||!l.search){return;}
var p=new URLSearchParams(l.search);
var o=p.get('o'),t=p.get('t');
if(!o||!t){return;}
window.history.replaceState(null,'',l.pathname+'#o='+encodeURIComponent(o)+'&t='+encodeURIComponent(t));
})();`}
    </Script>
  );
}

export function ConsentDefaults() {
  const defaults = SIGNALS.map((s) => `${s}:'denied'`).join(",");
  return (
    <Script id="sf-consent-default" strategy="beforeInteractive">
      {`window.dataLayer=window.dataLayer||[];
function gtag(){window.dataLayer.push(arguments);}
window.gtag=gtag;
gtag('consent','default',{${defaults},wait_for_update:500});
gtag('set','url_passthrough',true);
gtag('set','ads_data_redaction',true);
var c=null;try{c=window.localStorage.getItem('${STORAGE_KEY}');}catch(e){c=null;}
if(c==='granted'){gtag('consent','update',{${SIGNALS.map((s) => `${s}:'granted'`).join(",")}});}`}
    </Script>
  );
}

export function Analytics() {
  if (!GA4_ID) return null;
  return (
    <>
      <Script
        id="sf-gtag"
        strategy="afterInteractive"
        src={`https://www.googletagmanager.com/gtag/js?id=${GA4_ID}`}
      />
      <Script id="sf-gtag-config" strategy="afterInteractive">
        {`gtag('js',new Date());
// Task 31: gtag's own default for page_location is document.location.href, which
// still includes the fragment GalleryLinkRewrite just moved the key into. Only the
// gallery route needs the override — every other page keeps today's behaviour
// (default page_location), so gclid-based ad attribution elsewhere is untouched.
if(window.location.pathname==='/g/'){
gtag('config','${GA4_ID}',{page_path:'/g/',page_location:window.location.origin+'/g/'});
}else{
gtag('config','${GA4_ID}');
}`}
      </Script>
    </>
  );
}

function update(value: "granted" | "denied") {
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // Private mode: the choice applies to this page view and is asked again later.
  }
  window.gtag?.(
    "consent",
    "update",
    Object.fromEntries(SIGNALS.map((s) => [s, value])),
  );
}

export function ConsentBanner() {
  const [asked, setAsked] = useState(true);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      stored = null;
    }
    setAsked(stored !== null);
  }, []);

  return asked ? null : <Banner update={update} onAnswer={() => setAsked(true)} />;
}

function Banner({
  update,
  onAnswer,
}: {
  update: (v: "granted" | "denied") => void;
  onAnswer: () => void;
}) {
  const banner = useRef<HTMLDivElement>(null);

  /**
   * Reserve exactly as much room at the bottom of the document as the banner takes.
   *
   * It is `fixed bottom-0`, so at scroll position zero it sat ON TOP of whatever was
   * there. On /legal/terminos/ at 390x844 that was the last line of "Derecho de
   * desistimiento" — the citation of Real Decreto Legislativo 1/2007 itself, sliced
   * through the middle before the reader had interacted with anything. At 1440x900 it
   * clipped a different paragraph, so this was structural, not one bad breakpoint.
   * Obscuring statutory text on the page whose entire purpose is legal disclosure is
   * not a cosmetic problem.
   *
   * Measured rather than a magic number, because the banner wraps to three lines on a
   * narrow phone and one on a desktop.
   */
  useEffect(() => {
    const apply = () => {
      document.body.style.paddingBottom = `${banner.current?.offsetHeight ?? 0}px`;
    };
    apply();
    window.addEventListener("resize", apply);
    return () => {
      window.removeEventListener("resize", apply);
      document.body.style.paddingBottom = "";
    };
  }, []);

  const answer = (value: "granted" | "denied") => {
    update(value);
    onAnswer();
  };

  return (
    <div
      ref={banner}
      role="dialog"
      aria-label="Cookies"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-[color:var(--border)] bg-[color:var(--card)]"
    >
      <div className="sf-wrap sf-consent-row">
        <p className="sf-consent-text text-[color:var(--muted-foreground)]">
          Usamos cookies de medición y publicidad. Puedes aceptarlas o rechazarlas.{" "}
          <a className="sf-focus sf-consent-link underline" href="/legal/cookies/">
            Política de cookies
          </a>
        </p>
        {/* size="lg" (44px). These were the shadcn default of 32px — the two most
            tapped controls on the entire site, both under the tap-target floor, on a
            phone product.

            Both outlined since U4. "Aceptar" was filled in the accent red and
            "Rechazar" was not, so the two answers were not presented as equals. R6 went
            looking for the AEPD saying that in its own words and could not read the
            guide's PDF — recorded NOT CONFIRMED in docs/verified.md — and the brief says
            U4 applies either way. */}
        <div className="sf-consent-buttons">
          <Button size="lg" variant="outline" onClick={() => answer("denied")}>
            Rechazar
          </Button>
          <Button size="lg" variant="outline" onClick={() => answer("granted")}>
            Aceptar
          </Button>
        </div>
      </div>
    </div>
  );
}
