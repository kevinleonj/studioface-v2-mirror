"use client";

/**
 * Gallery. Reads ?o=<order>&t=<token> and polls every 3 s until delivered.
 *
 * The query string is read from window.location in an effect, not with
 * useSearchParams: this is a static export, and useSearchParams forces the whole
 * route into a client-side-rendering bailout that next build refuses without a
 * Suspense boundary. There is no server to read it anyway.
 *
 * Image URLs are signed and expire in 15 minutes, so they are fetched fresh on each
 * poll and never cached in the page.
 */

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { EVENTS, track } from "@/lib/track";

const POLL_MS = 3000;
// Stripe redirects the browser BEFORE it delivers the webhook, so for a few seconds after
// paying, a perfectly good link points at an order that does not exist yet and /api/orders
// answers 404. The server used to answer `pending` to paper over this, which meant somebody
// who never paid saw an endless pending gallery too.
//
// So the server tells the truth and this absorbs the race: keep polling through 404s for
// this long before believing one. Bounded, because a forged link must eventually stop
// rather than spin on somebody's phone until they close the tab.
const NOTFOUND_GRACE_MS = 60_000;
const SLOW_AFTER_MS = 180_000;
const SUPPORT = "hola@studioface.app";
// Four photos, four frames. The list is literal so the page cannot promise a number the
// pipeline does not deliver (core.Pipeline.run, min_deliverable=4).
const FRAMES = [1, 2, 3, 4];

type Status =
  | "loading"
  | "working"
  | "delivered"
  | "refunded"
  | "refund_pending"
  | "notfound";

export default function GalleryPage() {
  const [status, setStatus] = useState<Status>("loading");
  // F4. Which of the four have actually decoded, so each fades in on its own.
  const [loaded, setLoaded] = useState<Record<number, boolean>>({});
  const [images, setImages] = useState<string[]>([]);
  // F3. Signed to be saved, not displayed. Falls back to the visible address so an
  // older response shape still renders a working link.
  const [downloads, setDownloads] = useState<string[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // When this gallery was first opened, so a 404 can be told from "too early" (see
  // NOTFOUND_GRACE_MS) without the server having to lie about whether the order exists.
  const startedAt = useRef(Date.now());

  // Task 30, preview-survives. This page is only ever reached after a Checkout
  // Session paid — /api/gracias (app/main.py) redirects here solely once Stripe's
  // own payment_status is FULFILLABLE — or through a recovery link for an order
  // already paid before. Either way, upload-form.tsx's free-preview handle in
  // sessionStorage is for a purchase now made and must not resurface on a later
  // visit to the home page. The key literal must match upload-form.tsx's
  // HANDLE_STORAGE_KEY exactly; not shared through a module because this is the
  // only thing either file needs from the other.
  useEffect(() => {
    try {
      sessionStorage.removeItem("sf_preview_handle");
    } catch {
      // Nothing to clear if storage is unavailable; nothing else here breaks either.
    }
  }, []);

  const poll = useCallback(async (order: string, token: string) => {
    try {
      const res = await fetch(`/api/orders/${order}/${token}`);
      if (res.status === 404) {
        if (Date.now() - startedAt.current < NOTFOUND_GRACE_MS) {
          // Almost certainly the webhook has not landed yet. Keep waiting.
          setStatus("working");
          timer.current = setTimeout(() => poll(order, token), POLL_MS);
          return;
        }
        setStatus("notfound");
        return;
      }
      const data = await res.json();
      if (data.status === "delivered") {
        setImages(data.images ?? []);
        setDownloads(data.downloads ?? []);
        setStatus("delivered");
        // Fired here rather than on the purchase, because this is where the customer
        // actually receives the thing. The server-side `purchase` says the money moved;
        // the gap between the two is the product failing after being paid for.
        //
        // Guarded per order (never one flag, or delivering order B would look
        // already-told because order A set it) so a reload — the page itself says
        // "recarga la pagina para renovarlos" — or reopening the delivery email does
        // not send a second order_delivered for the same order. Wrapped in try/catch
        // like consent.tsx: private-mode Safari throws on localStorage access, and a
        // tracker that throws must not take the poll loop down with it.
        let alreadyTold = false;
        try {
          alreadyTold = window.localStorage.getItem(`sf-delivered-${order}`) === "1";
        } catch {
          alreadyTold = false;
        }
        if (!alreadyTold) {
          track(EVENTS.orderDelivered, { images: (data.images ?? []).length });
          try {
            window.localStorage.setItem(`sf-delivered-${order}`, "1");
          } catch {
            // Private mode: nothing persists, so a reload may fire again. Better than
            // losing the event outright when storage is unavailable.
          }
        }
        return;
      }
      if (data.status === "failed_refunded") {
        setStatus("refunded");
        return;
      }
      // Requested but not yet confirmed by the payment provider. Bizum refunds settle
      // asynchronously, so promising the money is back would be the same lie the
      // server used to tell. Both states are terminal: stop polling either way.
      if (data.status === "failed_refund_pending") {
        setStatus("refund_pending");
        return;
      }
      setStatus("working");
      timer.current = setTimeout(() => poll(order, token), POLL_MS);
    } catch {
      // A blip in the network is not a failed order: keep polling.
      setStatus("working");
      timer.current = setTimeout(() => poll(order, token), POLL_MS);
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const order = params.get("o");
    const token = params.get("t");
    if (!order || !token) {
      setStatus("notfound");
      return;
    }
    poll(order, token);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [poll]);

  return (
    <section className="sf-wrap pt-12 sm:pt-16">
      <h1 className="font-[family-name:var(--font-newsreader)] text-3xl sm:text-4xl">
        Tus fotos
      </h1>

      {/* O4/P10. These used to render the same block, so a customer whose order was
          already delivered read "Estamos revelando tus cuatro fotos" for about two
          seconds before the images appeared. The first paint must never assert
          something that may be false: while we are still asking, we say nothing. */}
      {status === "loading" ? <Loading /> : null}
      {status === "working" ? <Waiting /> : null}

      {status === "delivered" ? (
        <>
          <p className="mt-4 text-[color:var(--muted-foreground)]">
            Descarga cada foto. Los enlaces caducan a los 15 minutos; recarga la
            página para renovarlos.
          </p>
          {/* Same columns, same gap and same 4:5 as the frames that were standing here
              a second ago, so the photographs land where the placeholders were instead
              of shoving the page around at the one moment the customer is looking. */}
          <div className="mt-8 grid grid-cols-2 gap-[var(--s2)] lg:grid-cols-4">
            {images.map((src, i) => (
              <figure
                key={src}
                className="flex flex-col gap-[var(--s2)] bg-[color:var(--secondary)]"
              >
                <Image
                  src={src}
                  alt={`Foto de perfil ${i + 1}`}
                  width={800}
                  height={1000}
                  unoptimized
                  // The pipeline asks fal for 4:5, so the grid stays even.
                  // sf-land: moment 4. Staggered 40ms so the grid settles rather than
                  // flashing; the fourth ends at 370ms, inside the 400ms ceiling. The
                  // delay is a timing property, not an animated one.
                  onLoad={() => setLoaded((was) => ({ ...was, [i]: true }))}
                  // F4. The fade is keyed to this image's own load event, not to a
                  // timer: the frame below reserves the 4:5 box, so nothing moves when
                  // the picture arrives. Under prefers-reduced-motion the global guard
                  // in globals.css reduces the animation to 1ms.
                  className={`aspect-[4/5] w-full object-cover ${
                    loaded[i] ? "sf-land" : "opacity-0"
                  }`}
                />
                <a
                  // size: "lg" (44px). It was the shadcn default of 32px — on the one
                  // control a customer presses to collect the four photographs they
                  // paid 19,99 € for. Same bug as the 36px CTA, through a door
                  // tests/test_tap_targets.py did not know existed: a bare <a> styled
                  // with buttonVariants(), which no <Button> grep will ever find.
                  className={buttonVariants({ size: "lg" })}
                  href={downloads[i] ?? src}
                  download={`studioface-${i + 1}.jpg`}
                >
                  Descargar
                </a>
              </figure>
            ))}
          </div>
          <p className="mt-8 text-sm text-[color:var(--muted-foreground)]">
            Estas imágenes están generadas con inteligencia artificial a partir
            de tus fotos.
          </p>
        </>
      ) : null}

      {status === "refund_pending" ? (
        <Ending
          lead="No hemos podido generar tus fotos y hemos pedido la devolución del importe."
          detail="Tu banco aún la está procesando; suele tardar unos días. Las fotos que subiste se borran a los 7 días, como siempre."
          href="/"
          cta="Volver a intentarlo"
        />
      ) : null}

      {status === "refunded" ? (
        <Ending
          lead="No hemos podido generar tus fotos y te hemos devuelto el importe completo."
          detail="El reembolso tarda unos días en aparecer en tu banco. No tienes que hacer nada. Las fotos que subiste se borran a los 7 días."
          href="/"
          cta="Volver a intentarlo"
        />
      ) : null}

      {status === "notfound" ? (
        <Ending
          lead="Este enlace no es válido o ha caducado."
          detail="Los enlaces de tus fotos son privados y llevan un código. Si lo has perdido, te lo reenviamos al correo con el que hiciste el pedido."
          href="/recuperar/"
          cta="Recuperar mi enlace"
        />
      ) : null}
    </section>
  );
}

/**
 * The wait, which used to be a heading, one sentence and a bar frozen at 45%.
 *
 * `value={45}` measured nothing. A bar that reports a number it did not measure is
 * worse than no bar: it invites the customer to read a position, and the position is
 * invented. What is left is what is actually known — roughly how long it takes, the
 * four frames that are coming, and the fact that closing the page costs nothing because
 * the email is sent by the pipeline (app/emails.py) and not by this page.
 *
 * One state change, after three minutes, and nothing loops or animates. A person who
 * has just paid does not need the page to perform activity at them.
 */
function Frames({ label }: { label?: (n: number) => string }) {
  // F4. The same four reserved 4:5 boxes for both waiting states, so the layout
  // does not move between them or when the photographs arrive.
  return (
    <div className="mt-[var(--s3)] grid grid-cols-2 gap-[var(--s2)] lg:grid-cols-4">
      {FRAMES.map((n) => (
        <div
          key={n}
          className="flex aspect-[4/5] items-end border border-[color:var(--border)] bg-[color:var(--secondary)] p-[var(--s2)]"
        >
          <span className="text-sm text-[color:var(--muted-foreground)]">
            {label ? label(n) : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

function Loading() {
  // P10: the first paint must never assert something that may be false. While we
  // are still asking the server, the page claims nothing at all.
  return <Frames />;
}

function Waiting() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(t);
  }, []);

  return (
    <>
      <p className="mt-4 max-w-prose text-[color:var(--muted-foreground)]">
        Estamos revelando tus cuatro fotos. Suele tardar unos dos minutos y esta
        página se actualiza sola.
      </p>
      <p className="mt-[var(--s2)] max-w-prose">
        Puedes cerrar esta página. Cuando estén listas te enviamos el enlace por
        correo.
      </p>
      {slow ? (
        <p
          role="status"
          className="mt-[var(--s2)] max-w-prose text-[color:var(--muted-foreground)]"
        >
          Está tardando más de lo habitual. El pedido sigue en marcha y te
          avisamos por correo en cuanto termine.
        </p>
      ) : null}

      {/* task 12. No photo exists client-side here — this page is opened fresh from a
          link, nothing was ever uploaded in this browser — so the same sf-wait
          treatment (globals.css) dims and pulses the empty frame itself rather than a
          photograph. */}
      <div className="mt-[var(--s3)] grid grid-cols-2 gap-[var(--s2)] lg:grid-cols-4">
        {FRAMES.map((n) => (
          <div
            key={n}
            className="sf-wait flex aspect-[4/5] items-end border border-[color:var(--border)] bg-[color:var(--secondary)] p-[var(--s2)]"
          >
            <span className="text-sm text-[color:var(--muted-foreground)]">
              Foto {n} de 4
            </span>
          </div>
        ))}
      </div>

      <p className="mt-[var(--s3)] max-w-prose text-sm text-[color:var(--muted-foreground)]">
        Si no conseguimos generar las cuatro, cancelamos el pedido y te
        devolvemos el importe automáticamente, sin que tengas que pedirlo.
      </p>
    </>
  );
}

/**
 * Every terminal state, with somewhere to go.
 *
 * Measured: refunded ended at y=253 with the footer at 656 — 403px of blank under an
 * apology and no link. That is where a customer gives up, and it was three of the five
 * states on this page.
 */
function Ending({
  lead,
  detail,
  href,
  cta,
}: {
  lead: string;
  detail: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="mt-8 max-w-prose">
      <p>{lead}</p>
      <p className="mt-[var(--s2)] text-[color:var(--muted-foreground)]">
        {detail}
      </p>
      <a
        className={`${buttonVariants({ size: "lg" })} mt-[var(--s3)]`}
        href={href}
      >
        {cta}
      </a>
      <p className="mt-[var(--s3)] text-sm text-[color:var(--muted-foreground)]">
        ¿Necesitas ayuda? Escríbenos a{" "}
        <a className="sf-focus underline" href={`mailto:${SUPPORT}`}>
          {SUPPORT}
        </a>
        .
      </p>
    </div>
  );
}
