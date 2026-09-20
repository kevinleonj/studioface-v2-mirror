/**
 * The before/after pairs.
 *
 * The people in the "antes" images DO NOT EXIST — they were generated, because we have
 * no consenting models. The "despues" images are real output from the same pipeline a
 * customer's photos go through (scripts/make_demo_assets.py).
 *
 * Both facts are disclosed in the visible caption AND in every alt attribute. That is
 * not decoration: showing a generated person as a customer result would be a
 * misleading representation of results under Directive 2005/29/EC and Ley 3/1991, and
 * an undisclosed AI image under AI Act Art. 50. tests/test_demo_assets.py asserts both
 * against the BUILT HTML, so the disclosure cannot be dropped by editing this file.
 *
 * <picture> rather than next/image: this is a static export, the files are already
 * sized and encoded by the script, and a WebP with a JPG fallback is the whole job.
 *
 * ONE SHAPE. "pair" splits the width evenly, which is right in the gallery, where the
 * visitor is comparing and the two images are equals. The hero's "inset" shape was
 * deleted with unit U3: the hero is a comparison slider now (components/comparador.tsx),
 * and a variant with no caller is the clutter the rules in CLAUDE.md name directly.
 */

export const MUESTRAS = [
  { key: "mujer-40", who: "una mujer de unos 40 años" },
  { key: "hombre-30", who: "un hombre de unos 30 años" },
  { key: "hombre-25", who: "un hombre de unos 25 años" },
] as const;

export const CAPTION =
  "Persona ficticia generada con IA. El resultado se ha producido con el mismo proceso " +
  "por el que pasan tus fotos.";

type Item = (typeof MUESTRAS)[number];

const antesAlt = (item: Item) =>
  `Foto de móvil de ${item.who}, una persona ficticia generada con IA`;
const despuesAlt = (item: Item) =>
  `Resultado de StudioFace para ${item.who}, a partir de una foto generada con IA`;

function Shot({
  src,
  alt,
  eager,
  shape = "aspect-[4/5]",
}: {
  src: string;
  alt: string;
  eager?: boolean;
  shape?: string;
}) {
  // An eager shot in the hero IS the LCP element, and Lighthouse's lcp-discovery insight
  // scored 0 without this. Verified 18 Sep against MDN browser-compat-data rather than
  // the element's Baseline badge: Chrome 101, Firefox 132, Safari 17.2, standard track,
  // not experimental — and it is a hint, so anything older simply ignores it.
  return (
    <picture>
      <source srcSet={`/muestras/${src}.webp`} type="image/webp" />
      <img
        src={`/muestras/${src}.jpg`}
        alt={alt}
        width={480}
        height={600}
        loading={eager ? "eager" : "lazy"}
        fetchPriority={eager ? "high" : undefined}
        decoding="async"
        className={`${shape} w-full object-cover`}
      />
    </picture>
  );
}

/**
 * The label sits on an opaque paper chip, not directly on the photograph.
 * Over a photograph the contrast of a caption is whatever that photograph happens to
 * be at that corner — unmeasurable, and different per image. On paper it is ink on
 * paper, 16.1:1, the same on every pair. tests/test_contrast.py.
 */
function Chip({ children }: { children: string }) {
  return (
    <span className="bg-[color:var(--background)] px-[var(--s1)] py-[2px] text-sm text-[color:var(--foreground)]">
      {children}
    </span>
  );
}

function Pair({ item, eager }: { item: Item; eager?: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-px border border-[color:var(--border)] bg-[color:var(--border)]">
      <div className="relative bg-[color:var(--background)]">
        <span className="absolute left-2 top-2 z-10">
          <Chip>Antes</Chip>
        </span>
        <Shot src={`${item.key}-antes`} alt={antesAlt(item)} eager={eager} />
      </div>
      <div className="relative bg-[color:var(--background)]">
        <span className="absolute left-2 top-2 z-10">
          <Chip>Después</Chip>
        </span>
        <Shot src={`${item.key}-despues`} alt={despuesAlt(item)} eager={eager} />
      </div>
    </div>
  );
}

export function Muestra({ item, eager }: { item: Item; eager?: boolean }) {
  return (
    <figure className="m-0">
      <Pair item={item} eager={eager} />
      <figcaption className="mt-[var(--s1)] text-sm text-[color:var(--muted-foreground)]">
        {CAPTION}
      </figcaption>
    </figure>
  );
}
