"use client";

import { CedOverlayProvider } from "@/contexts/CedOverlayContext";
import { DriveMapProvider } from "@/contexts/DriveMapContext";
import { MapVoiceProvider } from "@/contexts/MapVoiceContext";
import { NavigationBridgeMount } from "@/components/navigation/NavigationBridgeMount";
import { SupportChatMount } from "@/components/support/SupportChatMount";

/** Providers cliente globales (soporte flotante, etc.) */
export function ClientShell({ children }: { children: React.ReactNode }) {
  return (
    <CedOverlayProvider>
      <DriveMapProvider>
        <MapVoiceProvider>
          {children}
          <NavigationBridgeMount />
          <SupportChatMount />
        </MapVoiceProvider>
      </DriveMapProvider>
    </CedOverlayProvider>
  );
}
