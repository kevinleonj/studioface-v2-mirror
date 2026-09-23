import { H2, LegalPage } from "@/components/legal-page";
import { SITE_URL } from "@/lib/config";

export const metadata = { title: "Términos — StudioFace" };

// Task 52 (structured-data-tells-the-truth). Google's merchant-listing page
// recommends nesting MerchantReturnPolicy under the Organization type, so it lives
// here, on the page that states the policy in prose, not on the Product pages that
// merely point at it by "@id". The text matches what this page actually says, two
// paragraphs below: custom digital content, the right of withdrawal lost once the
// images are delivered (artículo 103.m, Real Decreto Legislativo 1/2007), and — kept
// out of this node because it is not a return, it is a refund on non-delivery — the
// separate automatic full refund when the four images cannot be produced.
// returnPolicyCategory is MerchantReturnNotPermitted: no returnable window is
// invented, because none exists. merchantReturnLink points at #devoluciones, the id
// on the "Derecho de desistimiento" heading directly below, so the fragment is real.
const RETURN_POLICY_ID = `${SITE_URL}/legal/terminos/#devoluciones`;

const ORGANIZATION_RETURN_POLICY_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "StudioFace",
  url: SITE_URL,
  // Task 95d. The 180x180 apple-icon.png the app already serves.
  logo: "https://studioface.app/apple-icon.png",
  hasMerchantReturnPolicy: {
    "@type": "MerchantReturnPolicy",
    "@id": RETURN_POLICY_ID,
    applicableCountry: "ES",
    returnPolicyCategory: "https://schema.org/MerchantReturnNotPermitted",
    merchantReturnLink: RETURN_POLICY_ID,
  },
};

export default function Page() {
  return (
    <LegalPage title="Términos y condiciones" updated="23 de septiembre de 2026">
      <H2>Qué incluye el servicio</H2>
      <p>
        Por 19,99 €, IVA incluido, recibes cuatro imágenes de perfil generadas con inteligencia
        artificial a partir de las fotografías que subes. El precio mostrado es el precio final.
      </p>
      <H2>Cómo se contrata</H2>
      <p>
        Subes tus fotografías, ves una prueba gratuita y, si decides continuar, pagas mediante
        Stripe. Recibirás el enlace a tus imágenes por correo electrónico, normalmente en unos
        minutos.
      </p>
      <H2 id="devoluciones">Derecho de desistimiento</H2>
      <p>
        Se trata de contenido digital generado a medida. Al confirmar el pago aceptas que la
        ejecución comience de inmediato y reconoces que, una vez entregadas las imágenes, pierdes
        el derecho de desistimiento previsto en el artículo 103.m del Real Decreto Legislativo
        1/2007.
      </p>
      <H2>Si algo sale mal</H2>
      <p>
        Si no podemos entregar las cuatro imágenes, el pedido se cancela y se devuelve el importe
        íntegro de forma automática, sin que tengas que reclamarlo.
      </p>
      <H2>Uso aceptable</H2>
      <p>
        Solo puedes subir fotografías de ti mismo o de una persona que te haya autorizado. No se
        permite subir imágenes de menores ni de personas que no hayan dado su consentimiento.
      </p>
      <H2>Contacto</H2>
      <p>
        Titular: Kevin Daniel León Jouvin. NIF: Z3714124-C. Domicilio: Calle de Diego de León
        13, 7º A, 28006 Madrid. hola@studioface.app.{" "}
        <a className="sf-focus sf-consent-link underline" href="/sobre-nosotros/">
          Sobre nosotros
        </a>
      </p>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORGANIZATION_RETURN_POLICY_LD) }}
      />
    </LegalPage>
  );
}
