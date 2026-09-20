"use client";

/**
 * Upload -> Turnstile -> free preview -> Stripe Checkout.
 *
 * The browser never names an object in the bucket. /api/preview returns an opaque
 * handle (batch, n, t) signed by the server, and /api/checkout only accepts that
 * handle back. See app/main.py.
 */

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { MAX_FILES, PRICE_EUR, PRICE_LABEL, TURNSTILE_SITEKEY } from "@/lib/config";
import { clickIds, EVENTS, ga4Identifiers, track } from "@/lib/track";

type Handle = {
  wardrobe?: string;
  preview_url: string;
  batch: string;
  n: number;
  t: string;
};

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      // F1. reset() takes the id render() returned; getResponse() reads the current
      // token, which is how a refresh is detected when the callback does not re-fire.
      reset: (widgetId: string) => void;
      getResponse?: (widgetId: string) => string | undefined;
    };
  }
}

// F1. How long to wait for a fresh Turnstile token before telling the visitor the
// check failed. Tokens normally arrive in well under a second; this is the ceiling.
const REFRESH_TIMEOUT_MS = 10_000;

const ERRORS: Record<string, string> = {
  client_cap:
    "Has alcanzado el límite de pruebas gratuitas. Inténtalo dentro de una hora.",
  subnet_cap: "Demasiadas pruebas desde tu red. Inténtalo más tarde.",
  daily_cap:
    "Hoy se ha alcanzado el límite de pruebas gratuitas. Vuelve mañana.",
  turnstile:
    "La comprobación de seguridad ha caducado. Espera un momento y vuelve a intentarlo.",
  paused:
    "El servicio está pausado temporalmente. Vuelve a intentarlo más tarde.",
  checkout_not_configured: "El pago no está disponible ahora mismo.",
  bad_handle: "La sesión ha caducado. Vuelve a subir tus fotos.",
  // Unit F2. fal answered 422 and said exactly what was wrong; this is the product
  // saying it back. Before, every one of these arrived as a 500 the map did not know,
  // so they all collapsed into "No hemos podido generar la prueba."
  content_policy:
    "Esa imagen no ha pasado el filtro de contenido. Sube una foto tuya real, de frente y sin filtros.",
  undecodable_image:
    "No hemos podido abrir ese archivo. Puede estar dañado. Prueba con otra foto.",
  model_no_media_generated:
    "No hemos podido generar un retrato con esa foto. Prueba con otra en la que se te vea la cara de frente.",
  model_image_load_error:
    "No hemos podido leer esa imagen. Prueba con un JPG o un PNG.",
  model_image_too_large:
    "Esa foto es demasiado grande. Prueba con una más pequeña.",
};

function messageFor(detail: string | undefined, fallback: string): string {
  if (!detail) return fallback;
  if (ERRORS[detail]) return ERRORS[detail];
  if (detail.startsWith("upload_count"))
    return `Sube entre 1 y ${MAX_FILES} fotos.`;
  if (detail.startsWith("file_too_large"))
    return "Alguna foto supera los 12 MB.";
  if (detail.startsWith("unsupported_type"))
    return "Alguno de los archivos no es una imagen.";
  // Any fal refusal we have not written a sentence for yet still says more than the
  // fallback: it says the photo was the problem, not the service.
  if (detail.startsWith("model_"))
    return "El generador no ha podido usar esa foto. Prueba con otra en la que se te vea la cara de frente.";
  return fallback;
}

/**
 * The customer picks the GARMENT, not their gender.
 *
 * These keys must match app/guards.py WARDROBES exactly — the server refuses an
 * unknown one with 422 rather than quietly substituting a default, because the
 * alternative is someone paying for clothes they did not choose.
 *
 * Deliberately no "hombre/mujer" option. Asking would collect an identity attribute
 * in order to sell a photograph, and the only thing the prompt actually needs is the
 * clothing. See the reasoning in guards.py.
 */
const WARDROBES = [
  { key: "", label: "El del estilo elegido" },
  { key: "blazer-camisa", label: "Blazer y camisa blanca" },
  { key: "blusa-sastre", label: "Chaqueta sastre y blusa" },
  { key: "camisa-azul", label: "Camisa azul, sin corbata" },
  { key: "blusa-clara", label: "Blusa azul claro" },
  { key: "jersey-cuello-alto", label: "Jersey de cuello alto" },
  { key: "negro-basico", label: "Camiseta negra lisa" },
];

// F5. Measured from Cloud Run request logs, 30-day window, every successful
// /api/preview: 9.43, 10.04, 11.20, 11.26, 12.30 seconds. Median 11.20, slowest 12.30.
// The sentence rounds up past the slowest one rather than quoting the median, because
// a wait that beats the promise is a good surprise and one that misses it is not.
const PREVIEW_SECONDS = "unos 15 segundos";

const FRAME =
  "aspect-[4/5] w-full max-w-xs self-center rounded-xl " +
  "border border-[color:var(--border)] bg-[color:var(--secondary)]";

function Generating() {
  const [elapsed, setElapsed] = useState(0);
  const status = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    // O5: eleven seconds of one grey line and nothing else. A counter is the cheapest
    // honest signal that something is still happening - and it is the true number,
    // not a bar inventing a position on a track nobody is on.
    const tick = setInterval(() => setElapsed((n) => n + 1), 1000);
    status.current?.focus();
    return () => clearInterval(tick);
  }, []);

  return (
    <div className="flex flex-col gap-[var(--s2)]">
      {/* The 4:5 box the photograph will occupy, reserved now, so nothing below it
          moves when the image arrives. */}
      <div className={FRAME} />
      <p
        ref={status}
        tabIndex={-1}
        role="status"
        aria-live="polite"
        className="sf-focus text-center text-sm text-[color:var(--muted-foreground)]"
      >
        Preparando tu prueba. Suele tardar {PREVIEW_SECONDS}. Llevamos {elapsed}{" "}
        s.
      </p>
    </div>
  );
}

function labelFor(key: string): string {
  return (
    WARDROBES.find((w) => w.key === key)?.label ?? "la ropa del estilo"
  ).toLowerCase();
}

export function UploadForm() {
  const [files, setFiles] = useState<File[]>([]);
  const [wardrobe, setWardrobe] = useState("");
  const [handle, setHandle] = useState<Handle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // C1. The preview used to point at fal's content delivery network, which the
  // Content-Security-Policy has never allowed, so the browser refused it and the
  // visitor got the broken-image icon and a grey box about 500px tall. The address
  // is signed and same-policy now, but an image can still fail to load - a signed
  // URL lives 15 minutes - and a broken-image icon is never an acceptable answer.
  const [previewBroken, setPreviewBroken] = useState(false);
  // O11. Not an error: the upload was accepted, something in it was not.
  const [notice, setNotice] = useState("");
  // F6. Which garment the free preview was actually made with. The selector below
  // only appears AFTER the preview returns, so a customer who changes it is shown
  // one outfit and sold another unless the page says so.
  const [previewWardrobe, setPreviewWardrobe] = useState("");
  // F5. Focus lands here once the preview has decoded.
  const buyButton = useRef<HTMLButtonElement>(null);
  // F1. The widget id from render(), and a poll handle so a refresh in flight can be
  // cancelled if another one starts.
  const widgetId = useRef<string | null>(null);
  const polling = useRef<number | null>(null);
  const turnstileToken = useRef("");
  const widget = useRef<HTMLDivElement>(null);
  const rendered = useRef(false);
  const [challenge, setChallenge] = useState<
    "waiting" | "ready" | "failed" | "refreshing"
  >("waiting");

  /**
   * THE BUG THIS REPLACES, because it cost every sale in production.
   *
   * This effect used to open with
   *
   *     if (!TURNSTILE_SITEKEY || !widget.current || !window.turnstile) return;
   *
   * Next loads the Turnstile script `afterInteractive`, so it has NOT run when React
   * fires mount effects. Measured against studioface.app: window.turnstile is undefined
   * at t=0 and an object at t=500ms, and the container stayed at 0 children for the ten
   * seconds observed. The effect bailed once and never ran again, the token stayed "",
   * /api/preview answered 403, and every visitor was told "No hemos podido verificar que
   * no eres un robot" — which was not true and was not their fault.
   *
   * It is deterministic, not intermittent, so reloading never helped either.
   *
   * `turnstile.ready()` is Cloudflare's documented answer to exactly this
   * (docs/verified.md, 18 Sep 2026). The poll is for the window before the script has
   * defined `turnstile` at all, where `ready` does not exist yet to be called.
   */
  useEffect(() => {
    if (!TURNSTILE_SITEKEY) return;
    let cancelled = false;

    const render = () => {
      if (cancelled || rendered.current || !widget.current || !window.turnstile)
        return;
      // render() throws on a container that already holds a widget, and React runs
      // effects twice in development Strict Mode.
      rendered.current = true;
      // F1. The id render() returns is the ONLY handle reset() accepts, and nothing
      // kept it before, which is why there was no reset call anywhere in the bundle.
      widgetId.current = window.turnstile.render(widget.current, {
        sitekey: TURNSTILE_SITEKEY,
        callback: (token: string) => {
          turnstileToken.current = token;
          setChallenge("ready");
        },
        "error-callback": () => {
          // Say so here rather than at the moment they press the button, and do not
          // blame them for it.
          setChallenge("failed");
        },
        "expired-callback": () => {
          turnstileToken.current = "";
          setChallenge("failed");
        },
      });
    };

    // NOT turnstile.ready(). Cloudflare's own runtime refuses it here:
    //
    //   TurnstileError: [Cloudflare Turnstile] Remove async/defer from the Turnstile
    //   api.js script tag before using turnstile.ready().
    //
    // Next injects the tag async, so ready() throws and the widget still never renders.
    // That error is why this is a poll and not the first pattern in their docs — and it
    // only appeared because the fix was measured instead of assumed. Once
    // `window.turnstile` is an object, api.js has executed and render() is safe, which
    // is the same guarantee their `?onload=` callback gives.
    const start = render;

    if (window.turnstile) start();
    else {
      // The script has not defined `turnstile` yet, so there is nothing to call ready on.
      const timer = setInterval(() => {
        if (!window.turnstile) return;
        clearInterval(timer);
        start();
      }, 100);
      // Ten seconds is long past "the script is coming". After that, say so.
      const giveUp = setTimeout(() => {
        clearInterval(timer);
        if (!rendered.current && !cancelled) setChallenge("failed");
      }, 10000);
      return () => {
        cancelled = true;
        clearInterval(timer);
        clearTimeout(giveUp);
      };
    }

    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * F1. Spend the token, then get another one.
   *
   * O1: a Turnstile token is single-use and dies after five minutes, and the bundle
   * contained exactly one Turnstile call - `render`. So after any failed preview every
   * retry replayed a spent token and got 403 until the page was reloaded. Kevin's own
   * sequence: 500, 403, 200 after a reload, 403.
   *
   * The poll is not belt and braces. Cloudflare documents that `reset()` regenerates a
   * token, and does NOT document whether the fresh one arrives through the `callback`
   * given to `render()` - four of their pages were read and none says (docs/verified.md,
   * F1b). Assuming undocumented Turnstile behaviour is exactly what produced this
   * repository's earlier widget outage, so this works either way: the callback sets the
   * token if it fires, and the poll reads `getResponse` if it does not.
   */
  const refreshChallenge = useCallback(() => {
    if (!TURNSTILE_SITEKEY) return;
    const id = widgetId.current;
    if (!id || !window.turnstile) return;
    turnstileToken.current = "";
    setChallenge("refreshing");
    if (polling.current !== null) window.clearInterval(polling.current);
    window.turnstile.reset(id);

    const started = Date.now();
    polling.current = window.setInterval(() => {
      const fresh = window.turnstile?.getResponse?.(id) || "";
      if (fresh) {
        turnstileToken.current = fresh;
        setChallenge("ready");
      } else if (Date.now() - started > REFRESH_TIMEOUT_MS) {
        setChallenge("failed");
      } else {
        return;
      }
      if (polling.current !== null) window.clearInterval(polling.current);
      polling.current = null;
    }, 250);
  }, []);

  useEffect(
    () => () => {
      if (polling.current !== null) window.clearInterval(polling.current);
    },
    [],
  );

  const preview = useCallback(async () => {
    setBusy(true);
    setError("");
    setPreviewBroken(false);
    // H3's denominator. Fired before the request, not after: an upload that fails is
    // still an upload that was attempted, and the gap between started and ready is the
    // number the hypothesis turns on.
    track(EVENTS.previewStarted, { files: files.length });
    try {
      const body = new FormData();
      body.append("turnstile_token", turnstileToken.current);
      files.slice(0, MAX_FILES).forEach((file) => body.append("files", file));
      const res = await fetch("/api/preview", { method: "POST", body });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(messageFor(data.detail, "No hemos podido generar la prueba."));
        track(EVENTS.previewFailed, {
          reason: String(data.detail ?? res.status),
        });
        return;
      }
      setHandle(data as Handle);
      setPreviewWardrobe((data as Handle).wardrobe ?? "");
    } catch {
      setError("No hemos podido conectar. Comprueba tu conexión.");
      track(EVENTS.previewFailed, { reason: "network" });
    } finally {
      setBusy(false);
      // Every attempt spends the token, including the successful one - the visitor may
      // come back and try another photo.
      refreshChallenge();
    }
  }, [files, refreshChallenge]);

  const checkout = useCallback(async () => {
    if (!handle) return;
    setBusy(true);
    setError("");
    // The last click before Stripe owns the session. Anything after this is measured by
    // the server-side `purchase`, so this is the only place the drop-off can be seen.
    // GA4's own name for this step (docs/verified.md, Gg), with the shape it documents.
    track(EVENTS.beginCheckout, {
      value: PRICE_EUR,
      currency: "EUR",
      wardrobe: wardrobe || "por_defecto",
    });
    try {
      // Google's visitor and visit numbers, read from the tag already on this page.
      // Bounded (frontend/src/lib/track.ts): checkout must not hang on a callback
      // Google does not document as always firing.
      const ga4 = await ga4Identifiers();
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          batch: handle.batch,
          n: handle.n,
          t: handle.t,
          style: "corporativo",
          wardrobe: wardrobe || null,
          gclid: clickIds.gclid,
          gbraid: clickIds.gbraid,
          wbraid: clickIds.wbraid,
          ga_client_id: ga4.client_id,
          ga_session_id: ga4.session_id,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.url) {
        setError(messageFor(data.detail, "No hemos podido abrir el pago."));
        return;
      }
      window.location.href = data.url;
    } catch {
      setError("No hemos podido conectar con el pago.");
    } finally {
      setBusy(false);
    }
  }, [handle, wardrobe]);

  return (
    <div className="flex flex-col gap-4">
      {/* The drop target. Three things were wrong here and all three were states:
          hovering it did nothing at all (no rule existed), choosing a file exposed the
          raw 20px OS "Choose Files" control inside an otherwise hand-typeset page, and
          the chosen files were never named back to the buyer. The input is now
          visually hidden but still focusable, and the label reports the selection. */}
      <label
        htmlFor="sf-files"
        className="sf-frame block cursor-pointer border border-dashed border-[color:var(--border)] px-4 py-8 text-center hover:border-[color:var(--primary)] hover:bg-[color:var(--secondary)] has-[:focus-visible]:border-[color:var(--primary)]"
      >
        <span className="text-sm text-[color:var(--muted-foreground)]">
          {files.length === 0
            ? "Paso 01"
            : `${files.length} de ${MAX_FILES} elegidas`}
        </span>
        <span className="mt-[var(--s2)] block text-base font-medium">
          {files.length === 0
            ? `Sube de 1 a ${MAX_FILES} selfies`
            : "Elegir otras fotos"}
        </span>
        <span className="mt-[var(--s1)] block text-sm text-[color:var(--muted-foreground)]">
          {files.length === 0
            ? "JPG, PNG, WEBP o HEIC. Máximo 12 MB cada una."
            : files.map((f) => f.name).join(" · ")}
        </span>
        <input
          id="sf-files"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          multiple
          className="sr-only"
          onChange={(e) => {
            // O11. This used to store everything chosen, so picking five files rendered
            // "5 de 4 elegidas" and `files.slice(0, MAX_FILES)` silently dropped the
            // fifth at submit time. Count what is KEPT, and say what was not.
            const chosen = Array.from(e.target.files ?? []);
            const images = chosen.filter((f) => f.type.startsWith("image/"));
            const kept = images.slice(0, MAX_FILES);
            const rejected = chosen.length - images.length;
            const dropped = images.length - kept.length;
            setFiles(kept);
            setHandle(null);
            setPreviewBroken(false);
            setNotice(
              rejected > 0
                ? `Hemos ignorado ${rejected} ${rejected === 1 ? "archivo que no es una imagen" : "archivos que no son imágenes"}.`
                : dropped > 0
                  ? `Solo usamos las primeras ${MAX_FILES}. Hemos ignorado ${dropped} ${dropped === 1 ? "foto" : "fotos"}.`
                  : "",
            );
            if (kept.length > 0)
              track(EVENTS.uploadStart, { files: kept.length });
          }}
        />
      </label>

      {TURNSTILE_SITEKEY ? (
        <>
          <div ref={widget} className="min-h-[65px]" />
          {challenge === "refreshing" ? (
            <p
              role="status"
              className="text-sm text-[color:var(--muted-foreground)]"
            >
              Comprobando que eres una persona
            </p>
          ) : null}
          {challenge === "failed" ? (
            <p role="alert" className="text-sm text-[color:var(--destructive)]">
              No hemos podido cargar la comprobación de seguridad. Recarga la
              página o prueba con otra conexión.
            </p>
          ) : null}
        </>
      ) : null}

      {/* Was <Progress value={60} />. Sixty per cent of nothing: a literal, on the
          screen where the buyer is deciding whether to hand us four photographs. A
          status line says the true thing — that something is happening — without
          inventing a position on a track. */}
      {busy ? <Generating /> : null}

      {notice ? (
        <p
          role="status"
          className="text-sm text-[color:var(--muted-foreground)]"
        >
          {notice}
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-[color:var(--destructive)]">
          {error}
        </p>
      ) : null}

      {handle ? (
        <div className="flex flex-col gap-4">
          {previewBroken ? (
            <div
              role="alert"
              className="flex w-full max-w-xs flex-col gap-[var(--s2)] self-center rounded-xl border border-[color:var(--border)] p-[var(--s3)] text-center"
            >
              <p className="text-sm">
                No hemos podido mostrar tu prueba. El enlace de la imagen caduca
                a los 15 minutos.
              </p>
              <Button
                size="lg"
                variant="outline"
                onClick={() => {
                  setPreviewBroken(false);
                  setHandle(null);
                  // O1: without this, "Volver a intentarlo" walked straight into the
                  // same spent token and got 403.
                  refreshChallenge();
                }}
              >
                Volver a intentarlo
              </Button>
            </div>
          ) : (
            <Image
              src={handle.preview_url}
              alt="Prueba gratuita de tu foto de perfil"
              width={400}
              height={500}
              unoptimized
              onLoad={() => {
                track(EVENTS.previewReady);
                // F5. The wait is over and the next thing to do is buy. Moving focus
                // here is what makes that true for somebody on a keyboard or a screen
                // reader, not just for somebody looking at the screen.
                buyButton.current?.focus();
              }}
              onError={() => {
                setPreviewBroken(true);
                track(EVENTS.previewFailed, { reason: "image_blocked" });
              }}
              // sf-arrive: moment 3. The one moment in this product worth animating —
              // a stranger seeing their own face come back — and it used to snap.
              className="sf-arrive w-full max-w-xs self-center rounded-xl"
            />
          )}
          {/* Asked here rather than before the free preview: it is a choice about the
              four photos being bought, and one fewer decision between arriving and
              seeing something. */}
          <div className="flex flex-col gap-[var(--s1)]">
            <label
              htmlFor="sf-wardrobe"
              className="text-sm text-[color:var(--muted-foreground)]"
            >
              Ropa en las fotos
            </label>
            <select
              id="sf-wardrobe"
              className="sf-focus border border-[color:var(--border)] bg-[color:var(--background)] px-[var(--s2)] py-3 text-base"
              value={wardrobe}
              onChange={(e) => setWardrobe(e.target.value)}
            >
              {WARDROBES.map((w) => (
                <option key={w.key} value={w.key}>
                  {w.label}
                </option>
              ))}
            </select>
            {wardrobe && wardrobe !== previewWardrobe ? (
              <p
                role="status"
                className="text-sm text-[color:var(--muted-foreground)]"
              >
                Tu prueba se ha hecho con {labelFor(previewWardrobe)}. Las
                cuatro fotos finales usarán {labelFor(wardrobe)}.
              </p>
            ) : null}
          </div>
          <Button ref={buyButton} size="lg" disabled={busy} onClick={checkout}>
            Comprar las cuatro fotos por {PRICE_LABEL}
          </Button>
        </div>
      ) : (
        <Button
          size="lg"
          disabled={busy || files.length === 0 || challenge === "refreshing"}
          onClick={preview}
        >
          {busy ? "Generando tu prueba…" : "Ver una prueba gratis"}
        </Button>
      )}
    </div>
  );
}
