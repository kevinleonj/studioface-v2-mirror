import { H2, LegalPage } from "@/components/legal-page";

export const metadata = { title: "Términos — StudioFace" };

export default function Page() {
  return (
    <LegalPage title="Términos y condiciones">
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
      <H2>Derecho de desistimiento</H2>
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
        limeralda, NIF Z3714124-C, Maria de Molina 31, Madrid. hola@studioface.app.
      </p>
    </LegalPage>
  );
}
