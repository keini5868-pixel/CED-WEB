"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { fetchNavigationState } from "@/lib/api/navigation";
import { createClient } from "@/lib/supabase/client";

const POLL_MS = 2_000;

const NAV_POLL_PREFIXES = ["/dashboard", "/drive", "/historial", "/admin"];

function shouldPollNavigation(pathname: string | null): boolean {
  if (!pathname) return false;
  return NAV_POLL_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

/** Sincroniza acciones de voz (mapa, rutas) con la UI en rutas autenticadas. */
export function NavigationGlobalBridge() {
  const router = useRouter();
  const pathname = usePathname();
  const lastActionIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!shouldPollNavigation(pathname)) return;

    let cancelled = false;
    let timer: number | undefined;

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
        lastActionIdRef.current = action.id;

        if (action.action === "open_drive" && !pathname?.startsWith("/drive")) {
          router.push("/drive");
        }

        window.dispatchEvent(
          new CustomEvent("ced-navigation-event", { detail: action }),
        );
      } catch {
        /* sin sesión o sin estado — ignorar */
      }
    };

    void poll();
    timer = window.setInterval(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [pathname, router]);

  return null;
}
