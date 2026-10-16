import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Soporte — CED",
  robots: { index: false, follow: false },
};

export default function SoporteLayout({ children }: { children: ReactNode }) {
  return children;
}
