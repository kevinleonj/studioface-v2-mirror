import { H2, LegalPage } from "@/components/legal-page";

export const metadata = { title: "Privacidad — StudioFace" };

export default function Page() {
  return (
    <LegalPage title="Política de privacidad">
      <p>
        Esta política explica qué datos tratamos, con qué finalidad y durante cuánto tiempo, de
        acuerdo con el Reglamento (UE) 2016/679 y la Ley Orgánica 3/2018.
      </p>
      <H2>Responsable</H2>
      <p>
        limeralda, NIF Z3714124-C, con domicilio en Maria de Molina 31, Madrid. Contacto: hola@studioface.app.
      </p>
      <H2>Qué datos tratamos</H2>
      <p>
        Las fotografías que subes, tu dirección de correo electrónico y los datos del pago. El pago
        lo procesa Stripe: no vemos ni guardamos el número de tu tarjeta.
      </p>
      <H2>Para qué</H2>
      <p>
        Para generar las imágenes que solicitas y enviarte el enlace de descarga. La base jurídica
        es la ejecución del contrato. Las fotografías no se usan para entrenar modelos.
      </p>
      <H2>Cuánto tiempo</H2>
      <p>
        Las fotografías que subes se borran automáticamente a los 7 días. Las imágenes generadas se
        conservan 1 año para que puedas volver a descargarlas. Los datos de facturación se
        conservan durante los plazos legales.
      </p>
      <H2>Destinatarios</H2>
      <p>
        Prestadores que hacen posible el servicio: Google Cloud (alojamiento, Unión Europea),
        fal.ai (generación de imágenes), Stripe (pagos), Resend (correo) y Cloudflare (protección
        frente a abuso). Algunos pueden tratar datos fuera del Espacio Económico Europeo con las
        garantías previstas en el RGPD.
      </p>
      <H2>Tus derechos</H2>
      <p>
        Puedes solicitar acceso, rectificación, supresión, limitación, oposición y portabilidad
        escribiendo a hola@studioface.app. También puedes reclamar ante la Agencia Española de
        Protección de Datos.
      </p>
    </LegalPage>
  );
}
