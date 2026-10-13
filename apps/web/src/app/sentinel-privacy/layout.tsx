import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Sentinel Privacy — sellos verificables",
  description:
    "Producto aparte de CED: privacidad selectiva, sellos hash + tiempo (Midnight). Desde $12/mes.",
  alternates: {
    canonical: "https://ced-castillo.com/sentinel-privacy",
  },
};

export default function SentinelPrivacyLayout({ children }: { children: ReactNode }) {
  return children;
}
