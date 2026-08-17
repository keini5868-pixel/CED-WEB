"use client";

import type { ReactNode } from "react";

import { CedOverlayProvider } from "@/contexts/CedOverlayContext";
import { CedThemeProvider } from "@/contexts/CedThemeContext";
import { DriveMapProvider } from "@/contexts/DriveMapContext";
import { MapVoiceProvider } from "@/contexts/MapVoiceContext";
import { NavigationBridgeMount } from "@/components/navigation/NavigationBridgeMount";
import { SupportChatMount } from "@/components/support/SupportChatMount";

/** Providers cliente globales (soporte flotante, etc.) */
export function ClientShell({ children }: { children: ReactNode }) {
  return (
    <CedThemeProvider>
      <CedOverlayProvider>
        <DriveMapProvider>
          <MapVoiceProvider>
            {children}
            <NavigationBridgeMount />
            <SupportChatMount />
          </MapVoiceProvider>
        </DriveMapProvider>
      </CedOverlayProvider>
    </CedThemeProvider>
  );
}
