"use client";

/**
 * Task 95e. "¿Cómo nos encontraste?" - one optional question, rendered by the gallery
 * page ONLY inside its delivered block (frontend/src/app/g/page.tsx), so it never stands
 * between a visitor and paying. Answering is one tap; not answering costs nothing.
 *
 * The answer goes to POST /api/orders/{order}/found-us with the same key the gallery reads
 * the order with, in a header, never the address (task 31). The values must be exactly
 * app.found_us.FOUND_US; tests/test_found_us.py fails if the two lists drift.
 */

import { useState } from "react";
import { buttonVariants } from "@/components/ui/button";

const OPTIONS = [
  { value: "google", label: "Google" },
  { value: "chatgpt", label: "ChatGPT" },
  { value: "gemini", label: "Gemini" },
  { value: "claude", label: "Claude" },
  { value: "copilot", label: "Copilot" },
  { value: "social", label: "Instagram, TikTok o YouTube" },
  { value: "recomendacion", label: "Recomendación" },
  { value: "otro", label: "Otro" },
] as const;

export function FoundUs({ order, token }: { order: string; token: string }) {
  const [answered, setAnswered] = useState(false);

  async function answer(value: string) {
    // Say thanks straight away: the question is optional, and a slow or failed request
    // must never leave a customer who has already been paid for waiting on it.
    setAnswered(true);
    try {
      await fetch(`/api/orders/${order}/found-us`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Gallery-Token": token },
        body: JSON.stringify({ answer: value }),
      });
    } catch {
      // Optional by design: a lost answer is a missing data point, not an error to show.
    }
  }

  if (answered) {
    return <p className="mt-8 text-[color:var(--muted-foreground)]">Gracias por contárnoslo.</p>;
  }
  return (
    <section className="mt-8" aria-labelledby="found-us-question">
      <h2 id="found-us-question" className="text-lg font-medium">
        ¿Cómo nos encontraste?
      </h2>
      <p className="mt-1 text-[color:var(--muted-foreground)]">
        Opcional. Nos ayuda a saber dónde seguir contando que existimos.
      </p>
      <div className="mt-4 flex flex-wrap gap-[var(--s2)]">
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={buttonVariants({ variant: "outline", size: "lg" })}
            onClick={() => answer(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  );
}
