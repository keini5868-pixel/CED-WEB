"use client";

import { CedOverlayProvider } from "@/contexts/CedOverlayContext";
import { NavigationBridgeMount } from "@/components/navigation/NavigationBridgeMount";
import { SupportChatMount } from "@/components/support/SupportChatMount";

/** Providers cliente globales (soporte flotante, etc.) */
export function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <CedOverlayProvider>
      {children}
      <NavigationBridgeMount />
      <SupportChatMount />
    </CedOverlayProvider>
  );
}
