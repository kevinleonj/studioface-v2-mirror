"use client";

/**
 * The before/after comparison slider in the hero.
 *
 * Unit U3. It replaces the inset "Antes" thumbnail, which asked the visitor to compare
 * two photographs of different sizes in different corners of one frame. A slider puts
 * them in the same frame at the same scale, so the comparison is made for them.
 *
 * Why a real <input type="range"> under an opacity:0 layer rather than a div with pointer
 * handlers: the input already has the keyboard behaviour (arrows, Home, End), the touch
 * target, the drag, and the screen-reader semantics of a slider with a value. Every one
 * of those has to be rebuilt, badly, by anything else. The visible parts - the divider
 * and the round handle - are painted separately and take no pointer events, and the focus
 * ring is drawn on the handle because the element holding focus is invisible.
 *
 * The two files are cut by scripts/align_muestras.py so the faces are the same size and
 * the eyes are on the same line, within 0.05% and 0.03%. Without that the slider is worse
 * than the thumbnail it replaces: dragging it slides one face across a different face.
 *
 * No library and no animation. `clip-path: inset()` and `IntersectionObserver` are both
 * Baseline widely available (MDN, docs/verified.md), and the CSS carries no transition at
 * all, which is how "nothing animates on load" and "nothing at all under
 * prefers-reduced-motion" are satisfied at once.
 */

import { useEffect, useRef, useState } from "react";
import { CAPTION, MUESTRAS } from "@/components/muestras";
import { EVENTS, track } from "@/lib/track";

const HERO = MUESTRAS[0];

// The crops written by scripts/align_muestras.py. The originals stay where they are and
// are still what "Más muestras" shows.
const ANTES = `/muestras/${HERO.key}-antes-hero`;
const DESPUES = `/muestras/${HERO.key}-despues-hero`;
const W = 640;
const H = 800;

// Identical wording to the alt text the pair has always carried. Both facts - that the
// person is generated and that the result came from the real pipeline - are a disclosure
// under AI Act Art. 50 and Directive 2005/29/EC, not a caption style.
const ANTES_ALT = `Foto de móvil de ${HERO.who}, una persona ficticia generada con IA`;
const DESPUES_ALT = `Resultado de StudioFace para ${HERO.who}, a partir de una foto generada con IA`;

export function Comparador() {
  const [position, setPosition] = useState(50);
  const frame = useRef<HTMLDivElement>(null);

  // view_proof fires exactly where it fired before: once, when half the frame has been
  // seen. U3 says it keeps firing where it does today, so the observer moved with the
  // element rather than being rewritten around it.
  useEffect(() => {
    const el = frame.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        track(EVENTS.viewProof);
        io.disconnect();
      },
      // Half of it, so a pair clipped to a sliver by the consent banner does not count
      // as seen. Measured: at 390x844 the banner leaves a 691px slot.
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <figure className="m-0">
      <div ref={frame} className="sf-ba" style={{ "--p": `${position}%` } as React.CSSProperties}>
        <span className="sf-ba-tag sf-ba-tag-antes">Antes</span>
        <span className="sf-ba-tag sf-ba-tag-despues">Después</span>

        {/* Both eager and both in the first paint: the "después" is the LCP candidate and
            the "antes" is revealed by the very first drag, so lazy-loading it would show
            a hole where the comparison is. */}
        <picture>
          <source srcSet={`${DESPUES}.webp`} type="image/webp" />
          <img
            src={`${DESPUES}.jpg`}
            alt={DESPUES_ALT}
            width={W}
            height={H}
            loading="eager"
            fetchPriority="high"
            decoding="async"
          />
        </picture>
        <picture>
          <source srcSet={`${ANTES}.webp`} type="image/webp" />
          <img
            src={`${ANTES}.jpg`}
            alt={ANTES_ALT}
            width={W}
            height={H}
            loading="eager"
            decoding="async"
            className="sf-ba-antes"
          />
        </picture>

        <input
          type="range"
          min="0"
          max="100"
          value={position}
          aria-label="Comparar antes y después"
          className="sf-ba-range"
          onChange={(e) => setPosition(Number(e.target.value))}
        />
        <span className="sf-ba-divider" aria-hidden />
        {/* U+2194 with U+FE0E, the text-presentation selector. The bare arrow has an
            emoji presentation on some platforms and the skill bans emoji outright, so the
            selector is the difference between a typographic mark and a coloured glyph
            nobody chose. aria-hidden: the control beneath it already announces itself. */}
        <span className="sf-ba-handle" aria-hidden>
          {"↔︎"}
        </span>
      </div>
      <figcaption className="sf-ba-caption text-[color:var(--muted-foreground)]">
        {CAPTION}
      </figcaption>
    </figure>
  );
}
