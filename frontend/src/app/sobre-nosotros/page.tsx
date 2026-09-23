import { H2, LegalPage } from "@/components/legal-page";
import { SITE_URL } from "@/lib/config";

// Task 95d. Who runs StudioFace, for people and for search engines. Every fact here is
// already published on the legal pages (aviso legal, términos, the footer); nothing is
// added that they do not back - no team size, founding story, customer count or award.
// tests/test_about_page.py refuses the usual invented claims.
export const metadata = {
  title: "Sobre nosotros — StudioFace",
  description:
    "Quién está detrás de StudioFace: Kevin, desde Madrid. Titular, NIF, domicilio y " +
    "correo de contacto.",
  // Written out with its trailing slash: whether Next adds one under trailingSlash: true
  // is not confirmed (docs/verified.md, task 95 lines).
  alternates: { canonical: "https://studioface.app/sobre-nosotros/" },
};

// No sameAs: Kevin confirmed on 23 September 2026 that no public profile exists yet.
// Add one only the day it does.
const ORGANIZATION_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "StudioFace",
  url: SITE_URL,
  // The 180x180 apple-icon.png the app already serves; Google asks for at least 112x112.
  logo: "https://studioface.app/apple-icon.png",
  email: "hola@studioface.app",
};

export default function Page() {
  return (
    <LegalPage title="Sobre nosotros" updated="23 de septiembre de 2026">
      <p>
        StudioFace lo hace Kevin, desde Madrid. Subes tus selfies y recibes fotos de perfil
        profesionales generadas con inteligencia artificial a partir de ellas, sin fotógrafo
        ni estudio.
      </p>
      <H2>Quién presta el servicio</H2>
      <p>
        Titular: Kevin Daniel León Jouvin. NIF: Z3714124-C. Domicilio: Calle de Diego de León
        13, 7º A, 28006 Madrid.
      </p>
      <H2>Contacto</H2>
      <p>Para cualquier pregunta sobre tu pedido o tus fotos, escribe a hola@studioface.app.</p>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_LD) }}
      />
    </LegalPage>
  );
}
