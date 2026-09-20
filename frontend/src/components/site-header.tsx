/**
 * The header the page never had.
 *
 * There was no <header> element anywhere in the build. No wordmark, no route home, no
 * way to reach /recuperar/ except the footer of a page you had to scroll to the end of
 * — and a buyer who has lost their gallery link is exactly the person who will not
 * scroll patiently.
 *
 * What it deliberately is NOT: a SaaS navigation bar. This is one product with one
 * price; five links across the top would be pretending to be an application. It holds
 * the four things a buyer actually looks for and nothing else.
 *
 * Mobile decision: a compact PERSISTENT header, not a sticky bottom action bar.
 * The bottom 129px of every viewport already belongs to the consent banner until it is
 * dismissed, so a bottom bar would either sit on top of it or fight it for the same
 * thumb. The CTA it would carry is already the first interactive thing after the H1.
 * Measured, not assumed — see tests/test_header.py.
 *
 * `position: static`, not sticky: the skill forbids anything fixed covering content at
 * scroll 0, and a sticky header on a 844px-tall phone spends 56px of the first viewport
 * on chrome for a page you scroll once.
 */

import { PRICE_LABEL } from "@/lib/config";

const LINKS = [
  { href: "#como-funciona", label: "Cómo funciona" },
  { href: "/recuperar/", label: "Recuperar mis fotos" },
];

export function SiteHeader() {
  return (
    <header className="sf-header border-b border-[color:var(--border)]">
      <div className="sf-wrap sf-header-row">
        {/* One weight, one colour, no accented second syllable and no sheet number.
            The mark is the name. */}
        <a
          href="/"
          className="sf-focus sf-header-mark font-[family-name:var(--font-newsreader)] text-xl text-[color:var(--foreground)] no-underline"
        >
          StudioFace
        </a>

        <div className="flex items-center gap-x-[var(--s3)]">
          {/* Hidden below 900px by .sf-header-nav (unit U1): two links wrapping onto their
              own row cost 89px of a 390px phone's first screen. "Recuperar mis fotos"
              keeps its place in the footer and gains one directly under the uploader, so
              the buyer who lost their gallery link has not lost the route to it. */}
          <nav className="sf-header-nav text-sm">
            {LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="sf-focus inline-flex min-h-[44px] items-center text-[color:var(--foreground)] underline decoration-[color:var(--primary)] underline-offset-4"
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* "IVA incluido" travels with the price now, and the price stays on mobile
              while the links go. Measured: the block with "IVA incluido, pago único"
              renders at y=819 inside a 691px slot, so it is behind the consent banner on
              a first visit. A bare figure with no tax basis is not a price to a Spanish
              consumer. */}
          <span className="text-sm text-[color:var(--muted-foreground)]">
            {PRICE_LABEL} <span className="whitespace-nowrap">IVA incluido</span>
          </span>
        </div>
      </div>
    </header>
  );
}
