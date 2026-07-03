"use client";

import { useEffect, useMemo, useRef } from "react";
import { Navigation, Square } from "lucide-react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import type { NavRoute } from "@/lib/api/navigation";
import { distanceMeters, formatDistanceMeters } from "@/lib/navigation/geo";

type NavigationPanelProps = {
  route: NavRoute;
  position: GeoPosition | null;
  onStop: () => void;
  busy?: boolean;
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
    <div className="rounded-lg border border-purple-500/40 bg-black/90 p-4 shadow-xl backdrop-blur-md">
      <div className="mb-3 flex items-center gap-2">
        <Navigation className="h-5 w-5 text-purple-400" />
        <p className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-purple-300 sm:text-xs">
          NAVEGACIÓN ACTIVA
        </p>
      </div>

      <p className="mb-2 text-lg font-semibold leading-snug text-white sm:text-xl">
        {instruction}
      </p>

      {turnLabel ? (
        <p className="mb-2 text-sm text-cyan-300">
          Próximo giro en {turnLabel}
        </p>
      ) : null}

      <p className="mb-4 text-xs text-cyan-500">
        ETA {route.duration_text} · {route.distance_text} ·{" "}
        {route.destination.label}
      </p>

      <button
        type="button"
        onClick={onStop}
        disabled={busy}
        className="inline-flex items-center gap-2 rounded border border-red-500/50 bg-red-950/40 px-4 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-red-200 hover:bg-red-900/40 disabled:opacity-50"
      >
        <Square className="h-3.5 w-3.5" />
        DETENER NAVEGACIÓN
      </button>
    </div>
  );
}
