/**
 * Footer. The four legal links are a Google Ads requirement for this account
 * (docs/DESIGN.md), so they appear on every page, not only the landing page.
 */

const LINKS = [
  { href: "/legal/aviso-legal/", label: "Aviso legal" },
  { href: "/legal/privacidad/", label: "Privacidad" },
  { href: "/legal/terminos/", label: "Términos" },
  { href: "/legal/cookies/", label: "Cookies" },
  // The whole recovery path existed with nothing anywhere linking to it: a buyer who
  // closed the gallery tab and lost the email had no route back into the product.
  { href: "/recuperar/", label: "Recuperar mis fotos" },
];

export function SiteFooter() {
  return (
    <footer className="mt-[var(--s4)] border-t border-[color:var(--border)] py-[var(--s3)]">
      <div className="sf-wrap flex flex-col gap-[var(--s3)] text-sm text-[color:var(--muted-foreground)] sm:flex-row sm:items-start sm:justify-between">
        {/* Trader identity on EVERY page, not only inside the legal pages. LSSI-CE
            Art. 10, and it is also the cheapest trust signal a stranger can read. */}
        <div>
          <p className="font-[family-name:var(--font-newsreader)] text-lg text-[color:var(--foreground)]">
            StudioFace
          </p>
          <p className="mt-[var(--s1)] text-sm">
            Titular: Kevin Daniel León Jouvin. NIF: Z3714124-C. Domicilio: Calle de Diego de León
            13, 7º A, 28006 Madrid.
          </p>
        </div>
        <nav className="flex flex-wrap gap-x-[var(--s3)] gap-y-[var(--s1)]">
          {LINKS.map((link) => (
            <a
              key={link.href}
              className="sf-focus inline-flex min-h-[44px] items-center border-b border-[color:var(--primary)] text-[color:var(--foreground)] no-underline"
              href={link.href}
            >
              {link.label}
            </a>
          ))}
        </nav>
      </div>
      <p className="sf-wrap mt-[var(--s3)] max-w-[62ch] text-sm text-[color:var(--muted-foreground)]">
        Las imágenes se generan con inteligencia artificial a partir de las fotos que subes.
      </p>
    </footer>
  );
}
