"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { fetchNavigationState } from "@/lib/api/navigation";

/** Sincroniza acciones de voz (mapa, rutas) con la UI en toda la app. */
export function NavigationGlobalBridge() {
  const router = useRouter();
  const pathname = usePathname();
  const lastActionIdRef = useRef<number | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const state = await fetchNavigationState(true);
        const action = state.client_action;
        if (!action || action.id === lastActionIdRef.current) return;
        lastActionIdRef.current = action.id;

        if (action.action === "open_drive" && !pathname?.startsWith("/drive")) {
          router.push("/drive");
        }

        window.dispatchEvent(
          new CustomEvent("ced-navigation-event", { detail: action }),
        );
      } catch {
        /* ignore */
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 2_000);
    return () => window.clearInterval(timer);
  }, [pathname, router]);

  return null;
}
