import type { ReactNode } from "react";
import type { Metadata } from "next";

const TITLE = "CED Shield — Midnight demo";
const DESCRIPTION =
  "Verifiable seal: SHA-256 + live Lace wallet on Midnight preprod. The document stays in CED. No fake txid.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  robots: { index: true, follow: true },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://ced-castillo.com/shield",
    siteName: "CED",
    type: "website",
  },
  alternates: {
    canonical: "https://ced-castillo.com/shield",
  },
};

export default function ShieldLayout({
  children,
}: {
  children: ReactNode;
}) {
  return children;
}
