"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { NavigationGlobalBridge } from "@/components/navigation/NavigationGlobalBridge";
import { createClient } from "@/lib/supabase/client";

const POLL_PREFIXES = ["/dashboard", "/drive", "/historial", "/admin", "/app"];

function isProtectedRoute(pathname: string | null): boolean {
  if (!pathname) return false;
  return POLL_PREFIXES.some((p) => pathname.startsWith(p));
}

/** Solo monta el bridge de navegación con sesión activa en rutas protegidas. */
export function NavigationBridgeMount() {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!isProtectedRoute(pathname)) {
      setReady(false);
      return;
    }
    void (async () => {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!cancelled) setReady(Boolean(session?.access_token));
    })();
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (!ready) return null;
  return <NavigationGlobalBridge />;
}
