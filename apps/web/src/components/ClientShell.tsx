"use client";

import { SupportChatMount } from "@/components/support/SupportChatMount";

/** Providers cliente globales (soporte flotante, etc.) */
export function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <SupportChatMount />
    </>
  );
}
