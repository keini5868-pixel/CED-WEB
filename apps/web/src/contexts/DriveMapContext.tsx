"use client";

import dynamic from "next/dynamic";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import type { NavClientAction } from "@/lib/api/navigation";

export type MapVoiceHandlers = {
  searchPlace: (query: string) => Promise<void>;
  selectOption: (index: number) => Promise<void>;
  startNavigation: () => void;
  stopNavigation: () => Promise<void>;
  getRouteSummary: () => string | null;
};

type DriveMapContextValue = {
  isOpen: boolean;
  openDriveMap: (bootstrapAction?: NavClientAction | null) => void;
  closeDriveMap: () => void;
  registerMapVoiceHandlers: (handlers: MapVoiceHandlers | null) => void;
  mapVoiceHandlers: MapVoiceHandlers | null;
  consumeBootstrapAction: () => NavClientAction | null;
};

const DriveMapContext = createContext<DriveMapContextValue | null>(null);

const DriveModePage = dynamic(
  () =>
    import("@/components/navigation/DriveModePage").then((m) => m.DriveModePage),
  { ssr: false },
);

/** Fuera del hub de voz: sobrevive al overlay de conducir y recibe el bridge. */
const CedYoutubePlayerPanel = dynamic(
  () =>
    import("@/components/voice/CedYoutubePlayerPanel").then(
      (m) => m.CedYoutubePlayerPanel,
    ),
  { ssr: false },
);

export function DriveMapProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [mapVoiceHandlers, setMapVoiceHandlers] = useState<MapVoiceHandlers | null>(
    null,
  );
  const [bootstrapAction, setBootstrapAction] = useState<NavClientAction | null>(
    null,
  );

  const openDriveMap = useCallback((action?: NavClientAction | null) => {
    if (action) setBootstrapAction(action);
    setIsOpen(true);
  }, []);

  const closeDriveMap = useCallback(() => {
    setIsOpen(false);
    setBootstrapAction(null);
  }, []);

  const registerMapVoiceHandlers = useCallback(
    (handlers: MapVoiceHandlers | null) => {
      setMapVoiceHandlers(handlers);
    },
    [],
  );

  const consumeBootstrapAction = useCallback(() => {
    const action = bootstrapAction;
    if (action) setBootstrapAction(null);
    return action;
  }, [bootstrapAction]);

  const value = useMemo(
    () => ({
      isOpen,
      openDriveMap,
      closeDriveMap,
      registerMapVoiceHandlers,
      mapVoiceHandlers,
      consumeBootstrapAction,
    }),
    [
      isOpen,
      openDriveMap,
      closeDriveMap,
      registerMapVoiceHandlers,
      mapVoiceHandlers,
      consumeBootstrapAction,
    ],
  );

  return (
    <DriveMapContext.Provider value={value}>
      {children}
      {isOpen ? (
        <div
          className="fixed inset-0 z-[250] bg-black"
          role="dialog"
          aria-modal="true"
          aria-label="Modo conducir"
        >
          <DriveModePage embedded onClose={closeDriveMap} />
        </div>
      ) : null}
      {/* Después del overlay + portal interno → visible encima del mapa. */}
      <CedYoutubePlayerPanel />
    </DriveMapContext.Provider>
  );
}

export function useDriveMap() {
  const ctx = useContext(DriveMapContext);
  if (!ctx) {
    return {
      isOpen: false,
      openDriveMap: () => {},
      closeDriveMap: () => {},
      registerMapVoiceHandlers: () => {},
      mapVoiceHandlers: null,
      consumeBootstrapAction: () => null,
    };
  }
  return ctx;
}
