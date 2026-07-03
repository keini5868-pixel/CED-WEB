"use client";

import { useEffect, useRef } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import type { NavRoute } from "@/lib/api/navigation";
import { cancelBrowserNavigationSpeech, distanceMeters } from "@/lib/navigation/geo";

type Options = {
  position: GeoPosition | null;
  route: NavRoute | null;
  enabled?: boolean;
  onArrival?: () => void;
};

export function useNavigationGuide({
  position,
  route,
  enabled = true,
  onArrival,
}: Options) {
  const announcedRef = useRef<Record<string, boolean>>({});

  useEffect(() => {
    if (enabled) cancelBrowserNavigationSpeech();
  }, [enabled, route?.destination?.lat, route?.destination?.lng]);

  useEffect(() => {
    if (!enabled) {
      announcedRef.current = {};
    }
  }, [enabled, route?.destination?.lat, route?.destination?.lng]);

  useEffect(() => {
    if (!enabled || !route || !position) return;

    const destDist = distanceMeters(position, {
      lat: route.destination.lat,
      lng: route.destination.lng,
    });
    if (destDist < 35 && !announcedRef.current.arrived) {
      announcedRef.current.arrived = true;
      onArrival?.();
    }
  }, [enabled, position, route, onArrival]);
}
