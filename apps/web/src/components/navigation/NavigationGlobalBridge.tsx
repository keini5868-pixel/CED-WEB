"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { useDriveMap } from "@/contexts/DriveMapContext";
import { fetchNavigationState, type NavClientAction } from "@/lib/api/navigation";
import { createClient } from "@/lib/supabase/client";

const POLL_MS = 2_000;

const NAV_POLL_PREFIXES = ["/dashboard", "/drive", "/historial", "/admin", "/app"];

const MAP_ACTIONS = new Set([
  "open_drive",
  "close_drive",
  "begin_navigation",
  "apply_route",
  "show_place_options",
  "show_destination",
  "cancel_navigation",
]);

function shouldPollNavigation(pathname: string | null): boolean {
  if (!pathname) return false;
  return NAV_POLL_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function shouldOpenMapForAction(action: string): boolean {
  return (
    action === "open_drive" ||
    action === "begin_navigation" ||
    action === "apply_route" ||
    action === "show_place_options" ||
    action === "show_destination"
  );
}

/** Sincroniza acciones de voz (mapa, rutas) con la UI en rutas autenticadas. */
export function NavigationGlobalBridge() {
  const pathname = usePathname();
  const { openDriveMap, closeDriveMap, isOpen } = useDriveMap();
  const lastActionIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!shouldPollNavigation(pathname)) return;

    let cancelled = false;

    const dispatchAction = (action: NavClientAction) => {
      const openingFresh = !isOpen && shouldOpenMapForAction(action.action);

      if (action.action === "close_drive") {
        if (isOpen) closeDriveMap();
        return;
      }

      if (openingFresh) {
        openDriveMap(action);
        return;
      }

      if (action.action === "open_drive" && !isOpen) {
        openDriveMap(action);
        return;
      }

      window.dispatchEvent(
        new CustomEvent("ced-navigation-event", { detail: action }),
      );
    };

    const poll = async () => {
      if (cancelled) return;
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) return;

      try {
        const state = await fetchNavigationState(true);
        const action = state.client_action;
        if (!action || action.id === lastActionIdRef.current) return;
        if (!MAP_ACTIONS.has(action.action)) return;
        lastActionIdRef.current = action.id;
        dispatchAction(action);
      } catch {
        /* sin sesión o sin estado — ignorar */
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pathname, openDriveMap, closeDriveMap, isOpen]);

  return null;
}
