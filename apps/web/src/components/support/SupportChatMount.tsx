"use client";

import dynamic from "next/dynamic";

const SupportFloatingButton = dynamic(
  () => import("@/components/support/SupportFloatingButton"),
  { ssr: false },
);

const SUPPORT_ENABLED =
  process.env.NEXT_PUBLIC_SUPPORT_CHAT_ENABLED === "true";

/** Burbuja flotante de soporte — solo si NEXT_PUBLIC_SUPPORT_CHAT_ENABLED=true */
export function SupportChatMount() {
  if (!SUPPORT_ENABLED) return null;
  return <SupportFloatingButton />;
}
