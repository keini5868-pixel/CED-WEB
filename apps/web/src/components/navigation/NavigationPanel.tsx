"use client";

import { useEffect, useMemo, useRef } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import type { NavRoute } from "@/lib/api/navigation";
import { distanceMeters, formatDistanceMeters } from "@/lib/navigation/geo";

type NavigationPanelProps = {
  route: NavRoute;
  position: GeoPosition | null;
  onStop: () => void;
  busy?: boolean;
  /** Instrucción GPS hablada — solo panel mapa, no diálogo. */
  voiceCue?: string | null;
};

function stepInstruction(route: NavRoute, stepIndex: number): string {
  const step = route.steps?.[stepIndex];
  if (!step) return "Continúe por la ruta";
  const text = step.instruction?.trim();
  if (text) return text;
  return "Continúe por la ruta";
}

export function NavigationPanel({
  route,
  position,
  onStop,
  busy = false,
  voiceCue = null,
}: NavigationPanelProps) {
  const stepIndexRef = useRef(0);

  useEffect(() => {
    stepIndexRef.current = 0;
  }, [route.destination.lat, route.destination.lng]);

  const { stepIndex, distanceToTurn } = useMemo(() => {
    if (!position || !route.steps?.length) {
      return { stepIndex: 0, distanceToTurn: null as number | null };
    }
    let idx = stepIndexRef.current;
    if (idx >= route.steps.length) idx = route.steps.length - 1;
    const step = route.steps[idx];
    if (!step) return { stepIndex: 0, distanceToTurn: null };

    const dist = distanceMeters(position, step.end);
    if (dist < 25 && idx < route.steps.length - 1) {
      stepIndexRef.current = idx + 1;
      idx = stepIndexRef.current;
    }
    const active = route.steps[idx];
    const turnDist = active ? distanceMeters(position, active.end) : null;
    return { stepIndex: idx, distanceToTurn: turnDist };
  }, [position, route.steps]);

  const instruction = stepInstruction(route, stepIndex);
  const turnLabel =
    distanceToTurn != null ? formatDistanceMeters(distanceToTurn) : null;

  return (
    <div className="nav-active-panel border-b border-cyan-500/20 bg-black/85 px-4 pb-4 pt-[max(1rem,env(safe-area-inset-top))] backdrop-blur-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="current-instruction text-xl font-bold leading-snug text-white">
            {instruction}
          </p>

          {voiceCue ? (
            <p className="nav-voice-cue mt-2 text-sm font-medium text-cyan-300/90">
              {voiceCue}
            </p>
          ) : null}

          {turnLabel ? (
            <p className="next-turn mt-1 text-sm text-[#00ffff]">
              Próximo giro en {turnLabel}
            </p>
          ) : null}

          <p className="eta-bar mt-2 text-xs text-cyan-500">
            ETA {route.duration_text} · {route.distance_text}
          </p>
        </div>

        <button
          type="button"
          onClick={onStop}
          disabled={busy}
          className="stop-nav-btn shrink-0 rounded border border-red-500/50 bg-red-500/30 px-4 py-2 text-xs text-white hover:bg-red-500/40 disabled:opacity-50"
        >
          ⏹ DETENER
        </button>
      </div>
    </div>
  );
}
