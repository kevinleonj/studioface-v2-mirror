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
  // Task 29: null when the photos were stored without a generation — either the
  // free-preview limit was reached (`limited: true`) or the buy button re-backed a
  // purchase with a changed set of photos (`limited: false`, via
  // storeCurrentPhotosForBuy). /api/checkout verifies `t` identically either way.
  preview_url: string | null;
  batch: string;
  n: number;
  t: string;
  // True only when the free previews for this hour are used up and /api/preview
  // stored the photos instead of generating one. Absent (falsy) on every other
  // handle, including a store-only one made for a changed set of photos.
  limited?: boolean;
};

/**
 * Task 30, preview-survives. WHAT WAS MEASURED FIRST, 21 Sep: `handle` above lived
 * only in this component's React state. app/entry.py's `_checkout_factory` sends a
 * cancelled Stripe Checkout back to `cancel_url=f"{s.public_url}/?cancelado=1"` — the
 * plain home page, one inert query parameter nothing in frontend/src ever reads — so
 * that return, exactly like an ordinary reload, remounts this component from nothing
 * and takes the preview and the buy button with it. The next attempt then spends
 * another of the visitor's three tries an hour for nothing.
 *
 * Kept here is the storage strictly needed to restore the buy button: the signed
 * handle (batch, count, signature) and the clothing the preview was made with.
 * Nothing else — no photo, nothing identifying — which is also why this needs no
 * separate consent notice: it is storage the visitor's own request requires.
 * sessionStorage, not localStorage, so it dies with the tab, and every read and
 * write is wrapped in try/catch: private browsing and blocked site data can make
 * either one throw, and the page must still work with nothing restored.
 */
const HANDLE_STORAGE_KEY = "sf_preview_handle";

type StoredHandle = { batch: string; n: number; t: string; wardrobe?: string };

function readStoredHandle(): StoredHandle | null {
  try {
    const raw = sessionStorage.getItem(HANDLE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredHandle>;
    if (
      typeof parsed.batch === "string" &&
      parsed.batch &&
      typeof parsed.n === "number" &&
      typeof parsed.t === "string" &&
      parsed.t
    ) {
      return {
        batch: parsed.batch,
        n: parsed.n,
        t: parsed.t,
        wardrobe: typeof parsed.wardrobe === "string" ? parsed.wardrobe : undefined,
      };
    }
    return null;
  } catch {
    return null;
  }
}

function writeStoredHandle(h: StoredHandle | null): void {
  try {
    if (h === null) sessionStorage.removeItem(HANDLE_STORAGE_KEY);
    else sessionStorage.setItem(HANDLE_STORAGE_KEY, JSON.stringify(h));
  } catch {
    // Private browsing or blocked site data: the page still works for this visit,
    // it just will not survive a reload — never a reason to break the current one.
  }
}

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
  // Task 28. Was "ha caducado" (expired) — not what happened. The server only ever
  // says `turnstile` when `verify_turnstile` returned false, which is a check that
  // did NOT pass (a bad or reused token), not one that ran out of time.
  turnstile:
    "La comprobación de seguridad no ha pasado. Espera un momento y vuelve a intentarlo.",
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

// Task 29, never-block-a-buyer. Says exactly what the terms already promise — a
// stored batch and a chance to buy or come back — and nothing more: no promise of a
// preview later, no promise of when "within the hour" started for this visitor.
const LIMITED_MESSAGE =
  "Has usado tus pruebas gratis de esta hora. Puedes comprar tus cuatro fotos ahora o volver dentro de una hora.";

// F5. Measured from Cloud Run request logs, 30-day window, every successful
// /api/preview: 9.43, 10.04, 11.20, 11.26, 12.30 seconds. Median 11.20, slowest 12.30.
// The sentence rounds up past the slowest one rather than quoting the median, because
// a wait that beats the promise is a good surprise and one that misses it is not.
const PREVIEW_SECONDS = "unos 15 segundos";

const FRAME =
  "aspect-[4/5] w-full max-w-xs self-center overflow-hidden rounded-xl " +
  "border border-[color:var(--border)] bg-[color:var(--secondary)]";

// O13, task 12. The box used to stay empty for the whole wait. sf-wait (globals.css)
// dims, blurs and slowly pulses the visitor's own first chosen photo instead, so the
// wait shows their face becoming something rather than a blank rectangle. Decorative:
// the status paragraph below is what actually announces the wait to a screen reader.
function Generating({ photoUrl }: { photoUrl: string }) {
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
      <div className={FRAME}>
        {photoUrl ? (
          <img
            src={photoUrl}
            alt=""
            aria-hidden="true"
            className="sf-wait h-full w-full object-cover"
          />
        ) : null}
      </div>
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

type Thumb = { url: string; ext: string };

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot + 1).toUpperCase();
}

/**
 * Safari reports a HEIC/HEIF file with that MIME type; Chromium keeps the type empty
 * but the extension survives either way, so both are checked. Neither browser decodes
 * HEIC into an <img>, so those files get a labelled tile instead of a broken-image icon.
 */
function isHeic(file: File): boolean {
  const type = file.type.toLowerCase();
  if (type === "image/heic" || type === "image/heif") return true;
  const ext = extensionOf(file.name);
  return ext === "HEIC" || ext === "HEIF";
}

// O14, task 27. A duplicate is "the same file chosen again", not "a file that looks
// the same" — name, size and last-modified together are what the File API actually
// gives us, and forging all three at once is not something a second pick does by
// accident.
function fileKey(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

function sameFileSet(a: File[], b: File[]): boolean {
  if (a.length !== b.length) return false;
  const keysB = new Set(b.map(fileKey));
  return a.every((file) => keysB.has(fileKey(file)));
}

// Task 28. Mirrors app/guards.py's MAX_BYTES exactly, so a photo too large is
// refused for the same reason on both sides — the browser refusal just saves the
// visitor a round trip to hear it.
const MAX_UPLOAD_BYTES = 12 * 1024 * 1024;

/**
 * Task 31 (drop-the-refused-file). THE BUG THIS REPLACES: picking photos a second
 * time now ADDS (task 27), which was right, but a file the SERVER refused used to
 * stay in the kept set forever — every later attempt re-sent it and was refused
 * again, and the visitor could never get a preview.
 *
 * app/guards.py's validate_uploads names the offending file by its POSITION in the
 * batch it just received: `unsupported_type:<i>` or `file_too_large:<i>`. `files`
 * never exceeds MAX_FILES, so `files.slice(0, MAX_FILES)` — what preview() actually
 * POSTs — is `files` itself, in the same order, and index i maps straight back onto
 * it. Some refusals never name an index at all: `upload_count:<n>` counts files, not
 * one of them, and the image-model refusals (content_policy, undecodable_image,
 * model_*, in ERRORS above) come from ONE fal call over the whole batch, which has
 * no way to blame a single input. Those keep going through messageFor exactly as
 * before — nothing is removed, because guessing which file was at fault would be
 * worse than saying nothing.
 */
function refusedFileIndex(detail: string | undefined): number | null {
  const m = detail ? /^(?:unsupported_type|file_too_large):(\d+)$/.exec(detail) : null;
  return m ? Number(m[1]) : null;
}

type ChosenFiles = {
  toAdd: File[];
  rejected: number; // not image/*
  empty: number; // 0 bytes — the reviewer's upload that started this task
  oversized: number; // over MAX_UPLOAD_BYTES
  duplicates: number;
  dropped: number; // would exceed MAX_FILES
};

/** Pure so it is checkable on its own: what a single pick does to the kept set. */
function classifyChosenFiles(chosen: File[], existing: File[]): ChosenFiles {
  const images = chosen.filter((f) => f.type.startsWith("image/"));
  const rejected = chosen.length - images.length;
  const empty = images.filter((f) => f.size === 0).length;
  const oversized = images.filter((f) => f.size > MAX_UPLOAD_BYTES).length;
  const usable = images.filter((f) => f.size > 0 && f.size <= MAX_UPLOAD_BYTES);
  const existingKeys = new Set(existing.map(fileKey));
  const unique: File[] = [];
  let duplicates = 0;
  for (const file of usable) {
    const key = fileKey(file);
    if (existingKeys.has(key)) {
      duplicates += 1;
      continue;
    }
    existingKeys.add(key);
    unique.push(file);
  }
  const room = Math.max(0, MAX_FILES - existing.length);
  const toAdd = unique.slice(0, room);
  return { toAdd, rejected, empty, oversized, duplicates, dropped: unique.length - toAdd.length };
}

/** One line at a time, most serious first — matches the single-notice design this
 * dropzone already had before task 28 added the empty/oversized cases. */
function noticeFor(c: Omit<ChosenFiles, "toAdd">): string {
  if (c.rejected > 0)
    return `Hemos ignorado ${c.rejected} ${c.rejected === 1 ? "archivo que no es una imagen" : "archivos que no son imágenes"}.`;
  if (c.empty > 0)
    return `Hemos ignorado ${c.empty} ${c.empty === 1 ? "archivo vacío" : "archivos vacíos"}.`;
  if (c.oversized > 0)
    return `Hemos ignorado ${c.oversized} ${c.oversized === 1 ? "foto que supera los 12 MB" : "fotos que superan los 12 MB"}.`;
  if (c.dropped > 0)
    return `Solo puedes guardar ${MAX_FILES} fotos. Hemos ignorado ${c.dropped} ${c.dropped === 1 ? "foto" : "fotos"}.`;
  if (c.duplicates > 0)
    return `${c.duplicates === 1 ? "Esa foto ya estaba" : "Esas fotos ya estaban"} en tu selección.`;
  return "";
}

/**
 * Task 27. THE BUG THIS REPLACES: picking photos a second time called setFiles(kept)
 * with only the new selection, which threw away every photo kept from the first pick,
 * and setHandle(null) right next to it threw away the preview and the buy button with
 * it — for up to an hour, on Kevin's own first real sale. Picking again must ADD.
 *
 * Task 29 is what makes this function real: /api/preview's storage-only path
 * (`store_only=1`) stores the CURRENT files and signs a handle exactly the way a real
 * preview does, without calling the image model — the visitor already saw one, so a
 * second generation is not needed just to buy a changed set of photos. Bounded by the
 * same RateLimiter.check_store as the free-preview-limit path (app/main.py).
 */
async function storeCurrentPhotosForBuy(
  files: File[],
  turnstileToken: string,
): Promise<Handle> {
  const body = new FormData();
  body.append("turnstile_token", turnstileToken);
  body.append("store_only", "1");
  files.slice(0, MAX_FILES).forEach((file) => body.append("files", file));
  const res = await fetch("/api/preview", { method: "POST", body });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String(data.detail ?? res.status));
  return data as Handle;
}

/**
 * Task 30. GET /api/preview/{batch} (app/main.py's `_register_preview_resign`) — the
 * SAME `preview_token` verification /api/checkout uses, never a re-implementation.
 * A signed picture address dies in 15 minutes, so restoring the handle after a reload
 * needs a fresh one for the SAME stored result, never a new generation. Returns null
 * on any failure (a store-only handle with no picture ever generated, a network
 * error, or — if sessionStorage were ever tampered with — a made-up signature): the
 * caller still restores the handle itself so the buy button comes back, and
 * /api/checkout verifies batch/n/t again independently regardless.
 */
async function resignPreview(stored: StoredHandle): Promise<string | null> {
  try {
    const url = `/api/preview/${encodeURIComponent(stored.batch)}?n=${stored.n}&t=${encodeURIComponent(stored.t)}`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json().catch(() => ({}));
    return typeof data.preview_url === "string" ? data.preview_url : null;
  } catch {
    return null;
  }
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
  // O12. One blob URL per kept file, so the visitor sees the photo they are about to
  // send rather than just its name. The effect below returns ONE cleanup function;
  // React runs that same function both when `files` changes and when the component
  // unmounts, so there is a single code path to prove rather than two.
  const [thumbs, setThumbs] = useState<Thumb[]>([]);
  // O14. The exact files the CURRENT handle was made from, so the page can tell when
  // a later pick or removal has left the visitor looking at a different set of
  // photos than the one behind the preview they are looking at.
  const [previewedFiles, setPreviewedFiles] = useState<File[]>([]);
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

  // O12. Every URL this effect creates is revoked by the cleanup it returns - never by
  // a different function, so "revoked on change" and "revoked on unmount" are the same
  // assertion. React calls this exact cleanup before the effect re-runs (a new file
  // list) and one final time when UploadForm unmounts.
  useEffect(() => {
    const next: Thumb[] = files.map((file) => ({
      url: isHeic(file) ? "" : URL.createObjectURL(file),
      ext: extensionOf(file.name),
    }));
    setThumbs(next);
    return () => {
      next.forEach((thumb) => {
        if (thumb.url) URL.revokeObjectURL(thumb.url);
      });
    };
  }, [files]);

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
        theme: "light",
        language: "es",
        size: "flexible",
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

  // Task 29. F5 moves focus to the buy button once the preview IMAGE loads; a
  // limited answer never has one, so this is the same "the wait is over, here is
  // what to do next" move for that case.
  useEffect(() => {
    if (handle?.limited) buyButton.current?.focus();
  }, [handle]);

  // Task 30, preview-survives. Restores the handle a reload or a return from
  // Stripe's cancel redirect would otherwise have thrown away (see the module
  // docstring on HANDLE_STORAGE_KEY above for what was measured before this fix).
  // Runs once, on mount, before anything the visitor does — `files` and
  // `previewedFiles` both start empty either way, so `sameFileSet` still agrees they
  // match and the "you changed your photos" notice does not appear on a plain
  // restore. `preview_url` is fetched fresh (never trusted from storage: the signed
  // address dies in 15 minutes) and stays null on any failure, which renders the
  // same as the existing non-limited null case — nothing in the image slot, buy
  // button and clothing selector still there.
  useEffect(() => {
    const stored = readStoredHandle();
    if (!stored) return;
    let cancelled = false;
    resignPreview(stored).then((preview_url) => {
      if (cancelled) return;
      setHandle({
        batch: stored.batch,
        n: stored.n,
        t: stored.t,
        wardrobe: stored.wardrobe,
        preview_url,
      });
      setPreviewWardrobe(stored.wardrobe ?? "");
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Task 30. Kept in step with `handle` itself: a fresh handle is saved, and a
  // cleared one (checkout(), or the "generar una prueba nueva" reset below) removes
  // the stored one too, so a stale handle for a batch this tab has moved on from
  // never comes back on the next reload.
  useEffect(() => {
    if (!handle) {
      writeStoredHandle(null);
      return;
    }
    writeStoredHandle({
      batch: handle.batch,
      n: handle.n,
      t: handle.t,
      wardrobe: handle.wardrobe,
    });
  }, [handle]);

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
        const detail = data.detail as string | undefined;
        const idx = refusedFileIndex(detail);
        const base = messageFor(detail, "No hemos podido generar la prueba.");
        if (idx !== null && idx < files.length) {
          // Task 31. THE FIX: the server named this file, so drop exactly that one
          // and keep the rest — the useEffect above revokes its thumbnail address
          // the same way it does for removePhoto, because both just change `files`.
          // `base` is kept as the opening sentence (never replaced) so an existing
          // reader of that sentence, e.g. tests/e2e/test_funnel.py's
          // test_a_file_that_is_not_an_image_gets_its_own_sentence, still finds it.
          const dropped = files[idx];
          setFiles((prev) => prev.filter((_, i) => i !== idx));
          setError(
            `${base} Hemos quitado "${dropped.name}" de tus fotos. Puedes generar ` +
              "la prueba con las que quedan o añadir otra.",
          );
        } else {
          setError(base);
        }
        track(EVENTS.previewFailed, { reason: String(detail ?? res.status) });
        return;
      }
      // Task 29. A limited answer is still a 200 with a real, usable handle — never
      // the previewFailed(!res.ok) branch above, which would say a sentence about
      // photos that were never the problem. It gets its own event all the same, so
      // the funnel can count how often the free previews run out.
      if ((data as Handle).limited) track(EVENTS.previewFailed, { reason: "limit" });
      setHandle(data as Handle);
      setPreviewWardrobe((data as Handle).wardrobe ?? "");
      setPreviewedFiles(files.slice(0, MAX_FILES));
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
    // Task 34 (buy-with-changed-photos). A visitor who removes every photo after a
    // preview still holds a signed handle (see the buy button's own `disabled` guard
    // below), but there is nothing left to sell — app/guards.py's validate_uploads
    // would refuse 0 files as `upload_count:0` anyway; this is the client-side half
    // of that same refusal, never offering the click in the first place.
    if (!handle || files.length === 0) return;
    setBusy(true);
    setError("");
    // Task 27/29. The buy button must sell what the visitor is currently looking at,
    // not whatever the last successful preview happened to be made from. If a pick or
    // a removal since then has changed the kept set, the handle is refreshed FIRST via
    // the storage-only path — no new generation, the visitor already saw one.
    let active = handle;
    if (!sameFileSet(files, previewedFiles)) {
      try {
        active = await storeCurrentPhotosForBuy(files, turnstileToken.current);
      } catch (e) {
        setBusy(false);
        // Task 34 (buy-with-changed-photos). Mirrors preview()'s own fix (task 31,
        // refusedFileIndex above): storeCurrentPhotosForBuy calls the SAME
        // /api/preview endpoint and gets the SAME `unsupported_type:<i>` /
        // `file_too_large:<i>` shape back. Before this, a refused file added before
        // buying stayed in the kept set forever — every later press of "Comprar"
        // re-sent it and was refused again, with no way out.
        const detail = e instanceof Error ? e.message : undefined;
        const idx = refusedFileIndex(detail);
        const base = messageFor(
          detail,
          "Todavía no podemos comprar fotos distintas a las de tu prueba. Genera una prueba nueva con las fotos actuales.",
        );
        if (idx !== null && idx < files.length) {
          const dropped = files[idx];
          setFiles((prev) => prev.filter((_, i) => i !== idx));
          setError(
            `${base} Hemos quitado "${dropped.name}" de tus fotos. Puedes comprar ` +
              "con las que quedan o añadir otra.",
          );
        } else {
          setError(base);
        }
        return;
      }
      setHandle(active);
      setPreviewedFiles(files.slice(0, MAX_FILES));
      // The token storeCurrentPhotosForBuy just spent is single-use, same as the one
      // preview() spends in its own finally block.
      refreshChallenge();
    }
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
          batch: active.batch,
          n: active.n,
          t: active.t,
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
  }, [handle, wardrobe, files, previewedFiles, refreshChallenge]);

  const removePhoto = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // Task 28. No ticket yet — the human check has not delivered a fresh token — for
  // as long as the widget is loading, refreshing, or has failed. When Turnstile is
  // not configured at all (TURNSTILE_SITEKEY empty), there is nothing to wait for.
  const notReady = TURNSTILE_SITEKEY !== "" && challenge !== "ready";

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
            : files.length < MAX_FILES
              ? "Añadir más fotos"
              : "Elegir otras fotos"}
        </span>
        <span className="mt-[var(--s1)] block text-sm text-[color:var(--muted-foreground)]">
          {files.length === 0
            ? "JPG, PNG, WEBP o HEIC. Máximo 12 MB cada una."
            : files.map((f) => f.name).join(" · ")}
        </span>
        {thumbs.length > 0 ? (
          <div
            data-sf-thumbs
            className="mt-[var(--s2)] flex flex-wrap justify-center gap-[var(--s1)]"
          >
            {thumbs.map((thumb, i) => (
              <div key={i} className="relative">
                {thumb.url ? (
                  <img
                    src={thumb.url}
                    alt={`Foto elegida ${i + 1}`}
                    className="size-16 rounded-lg object-cover"
                  />
                ) : (
                  <div
                    role="img"
                    aria-label={`Foto elegida ${i + 1}`}
                    className="flex size-16 items-center justify-center rounded-lg border border-[color:var(--border)] bg-[color:var(--secondary)] text-xs font-medium text-[color:var(--muted-foreground)]"
                  >
                    {thumb.ext}
                  </div>
                )}
                {/* O14, task 27. A real <button>, not a label: labels forward an
                    unclaimed click to their control, and this one sits inside the
                    dropzone's own label for #sf-files. preventDefault +
                    stopPropagation is belt and braces against that, so removing a
                    photo can never also reopen the file picker. h-11/w-11 is 44px,
                    the tap-target floor tests/test_tap_targets.py holds everywhere
                    else on this page. */}
                <button
                  type="button"
                  aria-label={`Quitar foto ${i + 1}`}
                  className="sf-focus absolute -top-3 -right-3 flex h-11 w-11 items-center justify-center rounded-full border border-[color:var(--border)] bg-[color:var(--background)] text-base font-medium text-[color:var(--muted-foreground)] hover:text-[color:var(--foreground)]"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    removePhoto(i);
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : null}
        <input
          id="sf-files"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          multiple
          className="sr-only"
          onChange={(e) => {
            // O11/O14, task 27. THE BUG: this used to call setFiles(kept) with only
            // the new selection, which threw away whatever was kept from an earlier
            // pick — see storeCurrentPhotosForBuy above. Picking again now ADDS, up
            // to MAX_FILES, skipping any file already kept (same name, size and
            // last-modified — fileKey above). Task 28: an empty file or one over 12 MB
            // is refused here too, before it is ever sent, keeping the rest.
            const chosen = Array.from(e.target.files ?? []);
            // Cleared straight away, so choosing the SAME file again always fires
            // this handler again — without this, some browsers do not re-fire
            // `change` for an unchanged input value, and a removed photo could never
            // be picked a second time.
            e.target.value = "";
            const c = classifyChosenFiles(chosen, files);
            if (c.toAdd.length > 0) setFiles([...files, ...c.toAdd]);
            setPreviewBroken(false);
            setNotice(noticeFor(c));
            if (c.toAdd.length > 0)
              track(EVENTS.uploadStart, { files: c.toAdd.length });
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
      {busy ? <Generating photoUrl={thumbs[0]?.url ?? ""} /> : null}

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
          {/* Task 27. THE BUG THIS REPLACES: a new pick used to erase this whole
              block — preview, buy button and all — by nulling `handle`. Now the
              preview stays exactly as it was, and this is the only thing that
              changes: a plain statement of the two honest options, matching what
              storeCurrentPhotosForBuy above can and cannot do today. */}
          {!sameFileSet(files, previewedFiles) ? (
            <div className="flex flex-col gap-[var(--s1)]">
              <p
                role="status"
                className="text-sm text-[color:var(--muted-foreground)]"
              >
                Has cambiado las fotos. Puedes generar una prueba nueva o comprar
                con las fotos actuales.
              </p>
              <Button
                size="lg"
                variant="outline"
                onClick={() => {
                  setHandle(null);
                  setPreviewedFiles([]);
                  setPreviewBroken(false);
                  // O1: same reason "Volver a intentarlo" resets the token below.
                  refreshChallenge();
                }}
              >
                Generar una prueba nueva
              </Button>
            </div>
          ) : null}
          {handle.limited ? (
            // Task 29. The free previews for this hour are spent, but the handle is
            // real and /api/checkout accepts it: the clothing selector and the buy
            // button below are the "normal" ones, not a special-cased pair. Says only
            // what the terms already promise — a purchase now, or a return in an hour.
            <p
              role="status"
              className="text-sm text-[color:var(--foreground)]"
            >
              {LIMITED_MESSAGE}
            </p>
          ) : handle.preview_url === null ? null : previewBroken ? (
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
                  setPreviewedFiles([]);
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
          <Button
            ref={buyButton}
            size="lg"
            // Task 34. `handle` can outlive the photos it was made from — a visitor
            // who removes every kept photo still holds a signed handle from an
            // earlier preview — so this must check `files.length` too, not just
            // `busy`, the same way the free-preview button below already does.
            disabled={busy || files.length === 0}
            onClick={checkout}
          >
            Comprar las cuatro fotos por {PRICE_LABEL}
          </Button>
        </div>
      ) : (
        <Button
          size="lg"
          // Task 28. Before this, the button was only disabled while a token was
          // being refreshed after a previous attempt — the FIRST wait, before
          // Turnstile has ever delivered a ticket, did not disable it at all, so a
          // fast click sent an empty token and got 403. `notReady` covers every state
          // that is not "ready" — waiting, refreshing, failed — because none of them
          // has a ticket to spend.
          disabled={busy || files.length === 0 || notReady}
          onClick={preview}
        >
          {busy
            ? "Generando tu prueba…"
            : notReady
              ? "Comprobando que eres una persona"
              : "Ver una prueba gratis"}
        </Button>
      )}
    </div>
  );
}
