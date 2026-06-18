"use client";

import { CedOverlayProvider } from "@/contexts/CedOverlayContext";
import { SupportChatMount } from "@/components/support/SupportChatMount";

/** Providers cliente globales (soporte flotante, etc.) */
export function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <CedOverlayProvider>
      {children}
      <SupportChatMount />
    </CedOverlayProvider>
  );
}
