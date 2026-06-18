"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import {
  ackNavigationAction,
  fetchNavigationState,
  type NavRoute,
} from "@/lib/api/navigation";

export type NavigationMapState = {
  route: NavRoute | null;
  destinationPin: { lat: number; lng: number; label: string } | null;
};

type Options = {
  enabled?: boolean;
  micOn?: boolean;
  onMapUpdate?: (state: NavigationMapState) => void;
};

export function useNavigationVoiceBridge({ enabled = true, micOn = false, onMapUpdate }: Options) {
  const router = useRouter();
  const lastActionIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const poll = async () => {
      try {
        const state = await fetchNavigationState(true);
        if (state.route) {
          onMapUpdate?.({
            route: state.route,
            destinationPin: state.route.destination
              ? {
                  lat: state.route.destination.lat,
                  lng: state.route.destination.lng,
                  label: state.route.destination.label,
                }
              : null,
          });
        }

        const action = state.client_action;
        if (!action || action.id === lastActionIdRef.current) return;
        lastActionIdRef.current = action.id;

        if (action.action === "open_drive") {
          router.push("/drive");
        } else if (action.action === "show_destination") {
          const lat = Number(action.payload.lat);
          const lng = Number(action.payload.lng);
          const label = String(action.payload.label || "Destino");
          if (Number.isFinite(lat) && Number.isFinite(lng)) {
            onMapUpdate?.({
              route: null,
              destinationPin: { lat, lng, label },
            });
          }
        } else if (action.action === "apply_route") {
          const route = action.payload as unknown as NavRoute;
          if (route?.path?.length) {
            onMapUpdate?.({
              route,
              destinationPin: route.destination
                ? {
                    lat: route.destination.lat,
                    lng: route.destination.lng,
                    label: route.destination.label,
                  }
                : null,
            });
          }
        } else if (action.action === "cancel_navigation") {
          onMapUpdate?.({ route: null, destinationPin: null });
        }

        void ackNavigationAction(action.id);
        window.dispatchEvent(
          new CustomEvent("ced-navigation-event", { detail: action }),
        );
      } catch {
        /* ignore */
      }
    };

    const intervalMs = micOn ? 2_000 : 4_000;
    void poll();
    const timer = window.setInterval(() => void poll(), intervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, micOn, onMapUpdate, router]);
}
