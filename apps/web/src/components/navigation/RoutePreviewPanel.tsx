"use client";

import { MapPin, Play } from "lucide-react";

import type { NavRoute } from "@/lib/api/navigation";

type RoutePreviewPanelProps = {
  route: NavRoute;
  onStart: () => void;
  busy?: boolean;
};

export function RoutePreviewPanel({
  route,
  onStart,
  busy = false,
}: RoutePreviewPanelProps) {
  return (
    <div className="rounded-lg border border-cyan-500/40 bg-black/90 p-4 shadow-xl backdrop-blur-md">
      <div className="mb-3 flex items-center gap-2">
        <MapPin className="h-5 w-5 text-cyan-400" />
        <p className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-300 sm:text-xs">
          RUTA LISTA
        </p>
      </div>

      <p className="mb-1 text-lg font-semibold text-white">
        {route.destination.label}
      </p>
      <p className="mb-4 text-sm text-cyan-400">
        ETA {route.duration_text} · {route.distance_text}
      </p>

      <button
        type="button"
        onClick={onStart}
        disabled={busy}
        className="inline-flex w-full items-center justify-center gap-2 rounded border border-cyan-400/60 bg-cyan-950/50 px-4 py-3 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-widest text-cyan-100 hover:bg-cyan-900/50 disabled:opacity-50"
      >
        <Play className="h-4 w-4 fill-current" />
        INICIAR RUTA
      </button>
    </div>
  );
}
