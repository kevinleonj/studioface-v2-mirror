import type { Metadata } from "next";

/**
 * Unit F4/O9. `/g/` is a client component, so it cannot export metadata itself; a
 * layout can, and this is the smallest thing that gives the page both.
 *
 * The title was the generic site one, so a customer with several tabs open could not
 * tell which was their gallery.
 *
 * `noindex, nofollow` because a gallery URL carries an order id and a delivery token.
 * It is unguessable rather than secret, and a search engine that reached one would
 * publish somebody's photographs. Nothing links here, but a link pasted into a public
 * thread is all it takes.
 */
export const metadata: Metadata = {
  title: "Tus fotos | StudioFace",
  robots: { index: false, follow: false },
};

export default function GalleryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
