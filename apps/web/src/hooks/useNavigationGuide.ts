"use client";

import { useEffect, useRef } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import type { NavRoute, NavStep } from "@/lib/api/navigation";
import { distanceMeters, formatDistanceMeters, speakNavigation } from "@/lib/navigation/geo";

type Options = {
  position: GeoPosition | null;
  route: NavRoute | null;
  enabled?: boolean;
  onArrival?: () => void;
};

const ANNOUNCE_THRESHOLDS = [400, 150, 40] as const;

function maneuverPhrase(step: NavStep): string {
  const text = step.instruction.trim();
  if (text) return text;
  const map: Record<string, string> = {
    "turn-left": "Gira a la izquierda",
    "turn-right": "Gira a la derecha",
    "turn-slight-left": "Gira levemente a la izquierda",
    "turn-slight-right": "Gira levemente a la derecha",
    "uturn-left": "Da vuelta en U",
    "uturn-right": "Da vuelta en U",
    "straight": "Siga derecho",
    "ramp-left": "Tome la rampa a la izquierda",
    "ramp-right": "Tome la rampa a la derecha",
    "merge": "Incorpórese",
    "fork-left": "Manténgase a la izquierda en la bifurcación",
    "fork-right": "Manténgase a la derecha en la bifurcación",
    "roundabout-left": "En la glorieta, tome la salida indicada",
    "roundabout-right": "En la glorieta, tome la salida indicada",
  };
  return map[step.maneuver] ?? "Continúe por la ruta";
}

export function useNavigationGuide({
  position,
  route,
  enabled = true,
  onArrival,
}: Options) {
  const stepIndexRef = useRef(0);
  const announcedRef = useRef<Record<string, boolean>>({});

  useEffect(() => {
    if (!enabled || !route) {
      stepIndexRef.current = 0;
      announcedRef.current = {};
    }
  }, [enabled, route?.destination?.lat, route?.destination?.lng]);

  useEffect(() => {
    if (!enabled || !route || !position || !route.steps?.length) return;

    const steps = route.steps;
    let idx = stepIndexRef.current;
    if (idx >= steps.length) idx = steps.length - 1;

    const step = steps[idx];
    if (!step) return;

    const dist = distanceMeters(position, step.end);

    if (dist < 25 && idx < steps.length - 1) {
      stepIndexRef.current = idx + 1;
      announcedRef.current = {};
      return;
    }

    for (const threshold of ANNOUNCE_THRESHOLDS) {
      const key = `${idx}-${threshold}`;
      if (dist > threshold || announcedRef.current[key]) continue;
      announcedRef.current[key] = true;
      const phrase = maneuverPhrase(step);
      if (threshold <= 40) {
        speakNavigation(`Ahora, ${phrase}`);
      } else {
        speakNavigation(`En ${formatDistanceMeters(dist)}, ${phrase}`);
      }
      break;
    }

    const destDist = distanceMeters(position, {
      lat: route.destination.lat,
      lng: route.destination.lng,
    });
    if (destDist < 35 && !announcedRef.current.arrived) {
      announcedRef.current.arrived = true;
      speakNavigation("Ha llegado a su destino, señor.");
      onArrival?.();
    }
  }, [enabled, position, route, onArrival]);
}
