import { H2, LegalPage } from "@/components/legal-page";

export const metadata = { title: "Cookies — StudioFace" };

export default function Page() {
  return (
    <LegalPage title="Política de cookies">
      <p>
        Usamos cookies propias necesarias para que el sitio funcione y cookies de terceros de
        medición y publicidad que solo se activan si las aceptas.
      </p>
      <H2>Necesarias</H2>
      <p>
        Cloudflare Turnstile comprueba que no eres un sistema automatizado antes de generar la
        prueba gratuita. Guardamos tu elección sobre cookies en el almacenamiento local de tu
        navegador.
      </p>
      <H2>Medición y publicidad</H2>
      <p>
        Google Analytics 4 y Google Ads nos permiten saber cuántas personas llegan al sitio y
        cuáles completan un pedido. Hasta que las aceptas, estas herramientas funcionan en modo de
        consentimiento denegado: no escriben cookies ni identificadores publicitarios.
      </p>
      <H2>Cómo cambiar tu decisión</H2>
      <p>
        Puedes borrar el almacenamiento local de este sitio en los ajustes de tu navegador y se te
        volverá a preguntar la próxima vez que entres.
      </p>
    </LegalPage>
  );
}
