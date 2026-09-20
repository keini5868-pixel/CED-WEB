import type { Metadata } from "next";

import { ShieldDemoClient } from "./ShieldDemoClient";

export const metadata: Metadata = {
  title: "CED Shield — Midnight demo",
  description:
    "Sello verificable: hash + fecha en Midnight. Jarvis y la voz de CED no cambian.",
  robots: { index: false, follow: false },
};

export default function ShieldDemoPage() {
  return <ShieldDemoClient />;
}
