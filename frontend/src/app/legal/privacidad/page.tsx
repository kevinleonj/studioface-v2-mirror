import { H2, LegalPage } from "@/components/legal-page";

export const metadata = { title: "Privacidad — StudioFace" };

export default function Page() {
  return (
    <LegalPage title="Política de privacidad" updated="23 de septiembre de 2026">
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
        Prestadores que hacen posible el servicio. Google Cloud aloja el servicio y los datos en la
        Unión Europea. Estos otros pueden tratar datos fuera del Espacio Económico Europeo:
      </p>
      <ul className="flex list-disc flex-col gap-3 pl-5">
        <li>
          Stripe (pagos): contrata con nosotros Stripe Payments Europe, Limited, y los datos del
          pago llegan a Stripe, LLC en Estados Unidos al amparo del Marco de Privacidad de Datos
          UE-EE. UU. Su acuerdo incorpora además cláusulas contractuales tipo.{" "}
          <a className="sf-focus sf-consent-link underline" href="https://stripe.com/legal/dta">
            Acuerdo de transferencia de datos de Stripe
          </a>
        </li>
        <li>
          Resend (correo): guarda los datos en Estados Unidos, con cláusulas contractuales tipo.{" "}
          <a className="sf-focus sf-consent-link underline" href="https://resend.com/legal/dpa">
            Acuerdo de tratamiento de datos de Resend
          </a>
        </li>
        <li>
          fal.ai (generación de imágenes): puede tratar las fotografías fuera del Espacio
          Económico Europeo; fal no publica el país. Se aplican cláusulas contractuales tipo.{" "}
          <a className="sf-focus sf-consent-link underline" href="https://fal.ai/legal/data-processing-addendum">
            Acuerdo de tratamiento de datos de fal
          </a>
        </li>
        <li>
          Cloudflare (protección frente a abuso): puede tratar datos fuera del Espacio Económico
          Europeo; Cloudflare no publica el país. Se aplican cláusulas contractuales tipo.{" "}
          <a className="sf-focus sf-consent-link underline" href="https://www.cloudflare.com/cloudflare-customer-dpa/">
            Acuerdo de tratamiento de datos de Cloudflare
          </a>
          . Para mejorar su detección de bots, Cloudflare trata además esas señales de la
          comprobación de seguridad como responsable del tratamiento.{" "}
          <a className="sf-focus sf-consent-link underline" href="https://www.cloudflare.com/turnstile-privacy-policy/">
            Adenda de privacidad de Turnstile
          </a>
        </li>
        <li>
          Google Analytics 4 (medición) y Google Ads (publicidad): Google transfiere datos a
          Estados Unidos al amparo del Marco de Privacidad de Datos UE-EE. UU.{" "}
          <a className="sf-focus sf-consent-link underline" href="https://business.safety.google/adsdatatransfers/">
            Transferencias de datos de Google
          </a>
        </li>
      </ul>
      <p>
        Las cláusulas contractuales tipo son las de la Decisión de Ejecución (UE) 2021/914 de la
        Comisión. El Marco de Privacidad de Datos UE-EE. UU. es el de la Decisión de Ejecución
        (UE) 2023/1795 de la Comisión.
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
