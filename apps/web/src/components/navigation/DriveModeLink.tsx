"use client";

import { Navigation } from "lucide-react";

import { useDriveMap } from "@/contexts/DriveMapContext";

/** Abre el mapa como overlay fullscreen — la sesión de voz del dashboard sigue activa. */
export function DriveModeLink({ compact = false }: { compact?: boolean }) {
  const { openDriveMap } = useDriveMap();

  return (
    <button
      type="button"
      onClick={() => openDriveMap()}
      className={[
        "inline-flex items-center justify-center gap-2 rounded border font-[family-name:var(--font-orbitron)] font-bold tracking-wider transition",
        compact
          ? "border-cyan-500/50 bg-cyan-950/40 px-2 py-1.5 text-[9px] text-cyan-300 hover:border-cyan-400 sm:px-3 sm:py-2 sm:text-xs"
          : "w-full border-cyan-400/60 bg-gradient-to-r from-cyan-950/80 to-black/80 px-4 py-3 text-xs text-cyan-200 shadow-[0_0_20px_rgba(0,229,255,0.12)] hover:border-cyan-300 sm:text-sm",
      ].join(" ")}
    >
      <Navigation className={compact ? "h-3.5 w-3.5" : "h-4 w-4"} />
      {compact ? "MAPA" : "MODO CONDUCIR — MAPA + GPS"}
    </button>
  );
}
