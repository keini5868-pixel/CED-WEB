import type { Metadata } from "next";

import { PitchDeck } from "./PitchDeck";

export const metadata: Metadata = {
  title: "CED Shield — Wave 2 pitch",
  description:
    "Judge deck: dual-ledger seal on Midnight. Hash + Lace, content stays in CED. No fake txid.",
  openGraph: {
    title: "CED Shield — Wave 2 pitch",
    description:
      "Judge deck: dual-ledger seal on Midnight. Hash + Lace, content stays in CED. No fake txid.",
    url: "https://ced-castillo.com/shield/pitch",
    siteName: "CED",
    type: "website",
  },
  alternates: {
    canonical: "https://ced-castillo.com/shield/pitch",
  },
};

export default function ShieldPitchPage() {
  return <PitchDeck />;
}
