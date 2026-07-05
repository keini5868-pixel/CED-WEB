"use client";

import { useEffect, useMemo, useRef } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import type { NavRoute } from "@/lib/api/navigation";
import { distanceMeters, NAV_STEP_COMPLETE_M } from "@/lib/navigation/geo";
import {
  estimateRemaining,
  formatArrivalTime,
  formatMiles,
  maneuverIcon,
} from "@/lib/navigation/maneuvers";

type NavigationPanelProps = {
  route: NavRoute;
  position: GeoPosition | null;
  onStop: () => void;
  busy?: boolean;
  voiceCue?: string | null;
};

function stepInstruction(route: NavRoute, stepIndex: number): string {
  const step = route.steps?.[stepIndex];
  if (!step) return "Continúe por la ruta";
  const text = step.instruction?.trim();
  return text || "Continúe por la ruta";
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

  const { stepIndex, remainingM, remainingSec } = useMemo(() => {
    if (!position) {
      return {
        stepIndex: 0,
        remainingM: route.distance_m,
        remainingSec: route.duration_s,
      };
    }

    let idx = stepIndexRef.current;
    const steps = route.steps ?? [];
    if (steps.length) {
      if (idx >= steps.length) idx = steps.length - 1;
      const step = steps[idx];
      if (step) {
        const distToStepEnd = distanceMeters(position, step.end);
        if (distToStepEnd < NAV_STEP_COMPLETE_M && idx < steps.length - 1) {
          stepIndexRef.current = idx + 1;
          idx = stepIndexRef.current;
        }
      }
    }

    const destDist = distanceMeters(position, {
      lat: route.destination.lat,
      lng: route.destination.lng,
    });

    const ratio =
      route.distance_m > 0 ? Math.min(1, destDist / route.distance_m) : 1;
    const sec = Math.max(0, Math.round(route.duration_s * ratio));

    return { stepIndex: idx, remainingM: destDist, remainingSec: sec };
  }, [position, route]);

  const currentStep = route.steps?.[stepIndex];
  const nextStep = route.steps?.[stepIndex + 1];
  const instruction = voiceCue?.trim() || stepInstruction(route, stepIndex);
  const nextInstruction = nextStep
    ? stepInstruction(route, stepIndex + 1)
    : "Llegando al destino";
  const icon = maneuverIcon(currentStep?.maneuver);
  const { minutes } = estimateRemaining(
    route.distance_m,
    route.duration_s,
    remainingM,
  );

  return (
    <>
      <div
        className="nav-active-panel pointer-events-auto absolute left-0 right-0 top-0 z-[120] rounded-b-xl px-5 py-4 pt-[max(1rem,env(safe-area-inset-top))]"
        style={{ background: "#1a7340" }}
      >
        <div className="flex items-center gap-3">
          <span className="current-maneuver-icon shrink-0 text-[2rem] leading-none text-white">
            {icon}
          </span>
          <div className="min-w-0 flex-1">
            <p className="current-instruction text-lg font-bold leading-snug text-white sm:text-[1.35rem]">
              {instruction}
            </p>
            <p className="next-turn mt-1 text-sm text-[#90EE90]">
              Luego: {nextInstruction}
            </p>
          </div>
        </div>
      </div>

      <div
        className="pointer-events-auto absolute bottom-0 left-0 right-0 z-[120] flex items-center justify-between gap-4 px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
        style={{ background: "rgba(0,0,0,0.85)" }}
      >
        <div>
          <p className="eta-bar text-[1.75rem] font-bold leading-none text-[#4CAF50]">
            {minutes} min
          </p>
          <p className="mt-1 text-sm text-[#aaaaaa]">
            {formatMiles(remainingM)} · {formatArrivalTime(remainingSec)}
          </p>
        </div>
        <button
          type="button"
          onClick={onStop}
          disabled={busy}
          className="stop-nav-btn shrink-0 rounded-full px-6 py-3 text-base font-bold text-white disabled:opacity-50"
          style={{ background: "#e53935" }}
        >
          Salir
        </button>
      </div>
    </>
  );
}
