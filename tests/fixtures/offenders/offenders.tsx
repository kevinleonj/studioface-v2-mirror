// Every violation the TSX-scanning half of the suite claims to catch, in one file.
//
// tests/test_source_scanners.py points every registered Scanner at this and fails the
// ones that find nothing. That is the question item 2 asked: which of these were asleep?
//
// The comments here are load-bearing in the opposite direction from usual. Each one
// names the violation on the line below it, in the same words the scanner looks for, so
// a scanner that has NOT been taught to strip comments will match the comment instead of
// the code and pass for the wrong reason. If a scanner only ever matches in here and
// never in the product, look at this file first.

import { buttonVariants } from "@/components/ui/button";

export function Offenders() {
  return (
    <div>
      {/* a Button with no size prop: shadcn's default is 32px */}
      <Button type="submit" disabled={false}>
        Enviarme el enlace
      </Button>

      {/* buttonVariants with no size argument, on a bare anchor where no Button grep looks */}
      <a className={buttonVariants()} href="/x" download="y">
        Descargar
      </a>

      {/* a fake progress bar: the number is a literal and measures nothing */}
      <Progress value={45} aria-label="Generando" />

      {/* motion smuggled in through a Tailwind utility, outside the reduced-motion guard */}
      <span className="transition-all hover:opacity-80" />
      <span className="transition-colors" />
      <span className="animate-in fade-in" />

      {/* an arrival animation in markup that is server-rendered above the fold */}
      <figure className="sf-arrive" />
      <figure className="sf-land" />

      {/* a Cloudflare always-pass test site key shipped to production */}
      <div data-sitekey="1x00000000000000000000AA" />

      {/* the widget render race: a one-shot mount effect that gives up and never retries */}
      <script>{`useEffect(() => { if (!window.turnstile) return; }, []);`}</script>

      {/* the even 50/50 pair leaking into a hero that should be the inset shape */}
      <div className="grid grid-cols-2 gap-px" />

      {/* a browser request to an absolute origin: the third production outage */}
      <button onClick={() => fetch("https://api.studioface.app/api/preview")}>Cross-origin</button>

      {/* a funnel event fired from a call site, which is what a call site looks like */}
      <button onClick={() => track(EVENTS.checkoutClick, { wardrobe: "x" })}>Comprar</button>
    </div>
  );
}

function ButtonPrimitive(props: Record<string, unknown>) {
  // NOT an offender: the primitive is the component that defines the size, and a scanner
  // that flags this one is over-matching rather than guarding.
  return <button {...props} />;
}
