import { H2, LegalPage } from "@/components/legal-page";

export const metadata = { title: "Aviso legal — StudioFace" };

export default function Page() {
  return (
    <LegalPage title="Aviso legal">
      <p>
        En cumplimiento de la Ley 34/2002, de servicios de la sociedad de la información y de
        comercio electrónico, se facilitan los siguientes datos identificativos.
      </p>
      <H2>Titular</H2>
      <p>
        Titular: limeralda. NIF: Z3714124-C. Domicilio: Maria de Molina 31, Madrid. Correo de contacto: hola@studioface.app.
      </p>
      <H2>Objeto</H2>
      <p>
        Este sitio ofrece un servicio de generación de fotografías de perfil mediante inteligencia
        artificial a partir de las imágenes que sube la persona usuaria.
      </p>
      <H2>Propiedad intelectual</H2>
      <p>
        Conservas todos los derechos sobre las fotografías que subes. Las imágenes generadas se te
        entregan para que las uses sin limitación de finalidad, incluida la profesional.
      </p>
      <H2>Responsabilidad</H2>
      <p>
        El servicio se presta sin garantía de que un resultado concreto sea de tu agrado. Si no
        podemos entregar las cuatro imágenes de un pedido, se devuelve el importe íntegro.
      </p>
      <H2>Legislación aplicable</H2>
      <p>Esta relación se rige por la legislación española.</p>
    </LegalPage>
  );
}
