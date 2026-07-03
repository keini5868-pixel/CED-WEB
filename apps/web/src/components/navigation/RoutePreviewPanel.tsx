"use client";

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
    <div className="nav-start-panel rounded-lg border border-cyan-500/30 bg-black/90 p-4 shadow-xl backdrop-blur-md">
      <div className="destination-info mb-4">
        <p className="dest-name text-lg font-semibold text-white">
          {route.destination.label}
        </p>
        <p className="dest-eta mt-1 text-sm text-cyan-400">
          ETA {route.duration_text} · {route.distance_text}
        </p>
      </div>

      <button
        type="button"
        onClick={onStart}
        disabled={busy}
        className="start-nav-btn w-full rounded-lg border-none bg-[#00ffff] px-12 py-4 text-lg font-bold text-black hover:bg-cyan-300 disabled:opacity-50"
      >
        ▶ INICIAR
      </button>
    </div>
  );
}
