"use client";

/**
 * Recover a gallery link by email.
 *
 * The answer is always the same whether or not the address exists. Saying "no such
 * order" would turn this box into a way to test whether a given person bought.
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EVENTS, track } from "@/lib/track";

const SUPPORT = "hola@studioface.app";

const NOTES = [
  {
    title: "Usa el correo del pedido",
    body:
      "Tiene que ser el mismo con el que pagaste. Es el único dato con el que podemos " +
      "encontrar tus fotos, porque no hay cuenta ni contraseña.",
  },
  {
    title: "Si no llega, mira en spam",
    body:
      "El asunto es «Tus fotos de StudioFace ya están listas». En Gmail puede acabar en " +
      "la pestaña de Promociones.",
  },
  {
    title: "Los enlaces de descarga caducan",
    body:
      "Cada foto se descarga con un enlace que dura 15 minutos. Vuelve a abrir la página " +
      "de tus fotos y se renuevan solos.",
  },
  {
    title: "Guardamos tus fotos un año",
    body:
      "Los cuatro retratos quedan disponibles doce meses desde el pedido. Las selfies que " +
      "subiste se borran a los 7 días.",
  },
];

export default function RecoverPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Every arrival here is a gallery link that did not survive contact with a real inbox.
  // docs/CONVERSION.md H6 is the only hypothesis whose success looks like a SMALL number.
  useEffect(() => {
    track(EVENTS.recuperarView);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    // The form is noValidate on purpose. `type="email" required` hands the error state
    // to the browser, which renders an untranslated English bubble ("Please include an
    // '@'...") on an otherwise entirely Spanish product — and in a typeface and box we
    // do not control. The one error a buyer is most likely to see was the one state
    // nobody had designed.
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Escribe un correo válido, por ejemplo nombre@dominio.com.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/recuperar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        setError("No hemos podido enviar el enlace. Inténtalo más tarde.");
        return;
      }
      setSent(true);
    } catch {
      setError("No hemos podido conectar. Comprueba tu conexión.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sf-wrap pt-12 sm:pt-16">
      <h1 className="font-[family-name:var(--font-newsreader)] text-3xl sm:text-4xl">
        Recuperar mi enlace
      </h1>
      <p className="mt-4 max-w-prose text-[color:var(--muted-foreground)]">
        Escribe el correo con el que hiciste el pedido y te reenviamos el enlace a tus fotos.
      </p>

      {sent ? (
        <div className="mt-8 max-w-prose">
          <p>Si existe un pedido con ese correo, te hemos enviado el enlace.</p>
          <p className="mt-[var(--s2)] text-[color:var(--muted-foreground)]">
            Busca un mensaje de StudioFace con el asunto «Tus fotos de StudioFace ya están listas».
            Si no aparece en unos minutos, mira en la carpeta de spam o en la pestaña de
            Promociones.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="mt-8 flex max-w-md flex-col gap-4">
          <label htmlFor="sf-email" className="text-sm font-medium">
            Tu correo
          </label>
          <Input
            id="sf-email"
            type="email"
            autoComplete="email"
            aria-invalid={error ? true : undefined}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="tu@correo.com"
          />
          {error ? (
            <p role="alert" className="text-sm text-[color:var(--destructive)]">
              {error}
            </p>
          ) : null}
          {/* size="lg" (44px). It was shadcn's default 32px, on the only control a
              customer who has lost the link they already paid for can press. */}
          <Button size="lg" type="submit" disabled={busy || email.length === 0}>
            {busy ? "Enviando…" : "Enviarme el enlace"}
          </Button>
        </form>
      )}

      {/* Measured at 1440x900: the form ended at y=361 with the footer at 656 — 295px of
          blank under the one question this page asks. The person reading it has already
          paid and lost their link, and every one of these three facts is something they
          are about to need. Filling the canvas with what they need is not padding. */}
      <div className="mt-[var(--s5)] grid max-w-3xl gap-[var(--s3)] sm:grid-cols-2">
        {NOTES.map((note) => (
          <div key={note.title}>
            <h2 className="font-[family-name:var(--font-newsreader)] text-xl">{note.title}</h2>
            <p className="mt-[var(--s1)] text-[color:var(--muted-foreground)]">{note.body}</p>
          </div>
        ))}
      </div>

      <p className="mt-[var(--s4)] max-w-prose text-sm text-[color:var(--muted-foreground)]">
        ¿Nada de esto funciona? Escríbenos a{" "}
        <a className="sf-focus underline" href={`mailto:${SUPPORT}`}>
          {SUPPORT}
        </a>{" "}
        con el correo del pedido y lo miramos.
      </p>
    </section>
  );
}
