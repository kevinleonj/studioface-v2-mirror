"use client";

/**
 * The two supporting pairs, held back until somebody scrolls towards them.
 *
 * `loading="lazy"` was doing nothing. Measured at 390×844 on a served copy of the
 * export: all six photographs were fetched before the visitor scrolled a pixel, and
 * then scrolling to the end of a 3763px page added 0.0 KB. Chromium's lazy-load
 * distance-from-viewport on a fast connection is large enough to cover the whole
 * document, so the attribute is a hint this page never benefits from. 141.7 KB of two
 * people a visitor had not asked to see, on a phone, on a first visit.
 *
 * An IntersectionObserver is a mechanism rather than a hint. 400px of rootMargin means
 * they are already arriving by the time the section is on screen.
 *
 * The hero pair is NOT deferred. It is the LCP element and the reason the page is
 * credible; holding it back would cost in the one place the page cannot afford it.
 *
 * <noscript> carries the real markup for a visitor without JavaScript, because an
 * observer never fires for them, and a page that silently drops two thirds of its
 * evidence for those visitors has not solved the problem — it has moved it somewhere
 * nobody measures. tests/test_budgets.py asserts both halves.
 */

import { useEffect, useRef, useState } from "react";
import { MUESTRAS, Muestra } from "@/components/muestras";
import { CAPTION } from "@/components/muestras";

const REST = MUESTRAS.slice(1);

export function MoreMuestras() {
  const [show, setShow] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = anchor.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setShow(true); // No observer, no deferral: better a heavy page than an empty one.
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        setShow(true);
        io.disconnect();
      },
      { rootMargin: "400px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <>
      <div
        ref={anchor}
        className="mt-[var(--s3)] grid gap-[var(--s3)] sm:grid-cols-2"
      >
        {REST.map((item) =>
          show ? (
            <Muestra key={item.key} item={item} />
          ) : (
            // Reserves the height the real figure will take, BY CONSTRUCTION.
            //
            // The first version said "the same 4:5 frame ... so nothing jumps" and was
            // aspect-[2/1]. It was not the same frame and it did jump: the design critic
            // measured a 171px placeholder against a 279.875px figure at 342px wide, a
            // 63.7% shift the moment the photographs swap in. A pair is two 4:5 images
            // side by side, which is 8:5, and the caption underneath is two more lines.
            // So the placeholder is the figure, with the real caption text made
            // invisible — the height then matches because it is computed from the same
            // string, not because somebody picked a ratio that looked about right.
            <figure key={item.key} className="m-0">
              <div className="aspect-[8/5] border border-[color:var(--border)] bg-[color:var(--secondary)]" />
              <p aria-hidden className="mt-[var(--s1)] invisible text-sm">
                {CAPTION}
              </p>
            </figure>
          ),
        )}
      </div>

      <noscript>
        <div className="mt-[var(--s3)] grid gap-[var(--s3)] sm:grid-cols-2">
          {REST.map((item) => (
            <figure key={item.key} className="m-0">
              <div className="grid grid-cols-2 gap-px border border-[color:var(--border)] bg-[color:var(--border)]">
                <img
                  src={`/muestras/${item.key}-antes.jpg`}
                  alt={`Foto de móvil de ${item.who}, una persona ficticia generada con IA`}
                  width={480}
                  height={600}
                  className="aspect-[4/5] w-full object-cover"
                />
                <img
                  src={`/muestras/${item.key}-despues.jpg`}
                  alt={`Resultado de StudioFace para ${item.who}, a partir de una foto generada con IA`}
                  width={480}
                  height={600}
                  className="aspect-[4/5] w-full object-cover"
                />
              </div>
              <figcaption className="mt-[var(--s1)] text-sm text-[color:var(--muted-foreground)]">
                {CAPTION}
              </figcaption>
            </figure>
          ))}
        </div>
      </noscript>
    </>
  );
}
