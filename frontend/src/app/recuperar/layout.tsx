import type { Metadata } from "next";

/**
 * Unit F4/O9. Same reason as `/g/`: a client component cannot export metadata.
 *
 * `noindex, nofollow` because this page's only purpose is to send a delivery link to
 * an address somebody types in. It is a recovery door for people who already bought,
 * not a page anybody should arrive at from a search result.
 */
export const metadata: Metadata = {
  title: "Recuperar mis fotos | StudioFace",
  robots: { index: false, follow: false },
};

export default function RecuperarLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
