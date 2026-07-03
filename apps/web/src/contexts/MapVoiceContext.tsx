"use client";

import { createContext, useContext } from "react";

import type { MapVoiceHandlers } from "@/contexts/DriveMapContext";
import { useDriveMap } from "@/contexts/DriveMapContext";

type MapVoiceContextValue = {
  handlers: MapVoiceHandlers | null;
  isMapOpen: boolean;
};

const MapVoiceContext = createContext<MapVoiceContextValue>({
  handlers: null,
  isMapOpen: false,
});

/** Puente voz ↔ mapa — handlers registrados por DriveModePage cuando el overlay está abierto. */
export function MapVoiceProvider({ children }: { children: React.ReactNode }) {
  const { mapVoiceHandlers, isOpen } = useDriveMap();

  return (
    <MapVoiceContext.Provider value={{ handlers: mapVoiceHandlers, isMapOpen: isOpen }}>
      {children}
    </MapVoiceContext.Provider>
  );
}

export function useMapVoice() {
  return useContext(MapVoiceContext);
}
