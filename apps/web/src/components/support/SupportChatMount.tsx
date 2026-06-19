"use client";

import dynamic from "next/dynamic";

import { isSupportChatEnabled } from "@/lib/env";

const SupportChatMountInner = dynamic(
  () => import("@/components/support/SupportChatMountInner"),
  { ssr: false },
);

/** Activa por defecto; solo se oculta con NEXT_PUBLIC_SUPPORT_CHAT_ENABLED=false */
export function SupportChatMount() {
  if (!isSupportChatEnabled()) return null;
  return <SupportChatMountInner />;
}
