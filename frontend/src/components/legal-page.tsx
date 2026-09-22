/**
 * Shared shell for the four legal pages.
 *
 * The trader's identity is now filled in (limeralda, NIF Z3714124-C, Maria de Molina
 * 31, Madrid). The Pending component that used to paint a visible [PENDIENTE] mark is
 * deleted rather than left unused: an unused placeholder is an invitation to ship
 * another one. tests/test_legal_identity.py fails if any page renders one again.
 */

export function LegalPage({
  title,
  updated = "17 de septiembre de 2026",
  children,
}: {
  title: string;
  updated?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="sf-wrap pt-12 sm:pt-16">
      <h1 className="font-[family-name:var(--font-newsreader)] text-3xl sm:text-4xl">{title}</h1>
      <p className="mt-2 text-sm text-[color:var(--muted-foreground)]">
        Última actualización: {updated}
      </p>
      <div className="mt-8 flex max-w-prose flex-col gap-4 text-[color:var(--muted-foreground)]">
        {children}
      </div>
    </section>
  );
}


export function H2({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <h2 id={id} className="mt-4 text-xl font-medium text-[color:var(--foreground)]">
      {children}
    </h2>
  );
}
