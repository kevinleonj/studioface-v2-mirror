"use client";

/**
 * The first product action on the page.
 *
 * Unit U5. F3, measured across 24 sites in the category: StudioFace was the only one with
 * no primary call to action inside the first 844px. The only product button was the
 * uploader's submit at y=1283, against a usable first viewport of 691px on a 390px phone,
 * and it rendered in its disabled style because no file had been chosen yet.
 *
 * So this is an anchor, not a second submit. It always works, because there is nothing it
 * needs from the visitor first: it takes them to the uploader and puts the cursor in it.
 * A disabled button on the first screen answers "can I try this?" with "no".
 *
 * The scroll is the browser's - `href="#subir"` with `scroll-behavior: smooth` in the
 * stylesheet, which the global prefers-reduced-motion guard already forces back to
 * `auto !important`. That is U5's "instantly under reduced motion", and it costs no
 * JavaScript and no media query of its own.
 *
 * Focus moves with `preventScroll`, so the anchor's own scrolling decides the position
 * and the focus call does not fight it. The uploader's label carries
 * `has-[:focus-visible]` styling, so landing there is visible rather than silent.
 */

import { EVENTS, track } from "@/lib/track";
import { PRICE_LABEL } from "@/lib/config";

export const UPLOADER_ID = "subir";

export function FoldCta({ location = "fold" }: { location?: "fold" | "sticky" }) {
  return (
    <>
      <a
        href={`#${UPLOADER_ID}`}
        data-cta={location}
        className="sf-cta sf-focus"
        onClick={() => {
          track(EVENTS.ctaClick, { location });
          document
            .getElementById(UPLOADER_ID)
            ?.querySelector<HTMLElement>('input[type="file"]')
            ?.focus({ preventScroll: true });
        }}
      >
        Ver mi prueba gratis
      </a>
      <p data-cta-micro className="sf-cta-micro">
        Sin registro ni tarjeta. {PRICE_LABEL} solo si te gusta.
      </p>
    </>
  );
}
