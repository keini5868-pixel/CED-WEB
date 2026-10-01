import type { Metadata } from "next";

import { ShieldDemoClient } from "./ShieldDemoClient";

export const metadata: Metadata = {
  title: "CED Shield — Midnight demo",
  description:
    "Verifiable seal: SHA-256 + live Lace wallet on Midnight preprod. Jarvis and CED voice stay off this path.",
  robots: { index: false, follow: false },
};

export default function ShieldDemoPage() {
  return <ShieldDemoClient />;
}
