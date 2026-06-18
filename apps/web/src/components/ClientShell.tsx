"use client";

import { CedOverlayProvider } from "@/contexts/CedOverlayContext";
import { NavigationGlobalBridge } from "@/components/navigation/NavigationGlobalBridge";
import { SupportChatMount } from "@/components/support/SupportChatMount";

/** Providers cliente globales (soporte flotante, etc.) */
export function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <CedOverlayProvider>
      {children}
      <NavigationGlobalBridge />
      <SupportChatMount />
    </CedOverlayProvider>
  );
}
