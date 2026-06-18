"use client";

import dynamic from "next/dynamic";

const SupportFloatingButton = dynamic(
  () => import("@/components/support/SupportFloatingButton"),
  { ssr: false },
);

/** Activa por defecto; solo se oculta con NEXT_PUBLIC_SUPPORT_CHAT_ENABLED=false */
export function SupportChatMount() {
  if (process.env.NEXT_PUBLIC_SUPPORT_CHAT_ENABLED === "false") return null;
  return <SupportFloatingButton />;
}
