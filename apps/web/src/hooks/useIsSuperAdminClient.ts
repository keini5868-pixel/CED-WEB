"use client";

import { useEffect, useState } from "react";

import { isSuperAdmin } from "@/lib/auth/roles";
import { cedApiPath } from "@/lib/api/ced-proxy";
import { createClient } from "@/lib/supabase/client";

/** Detecta super admin en cliente (misma lógica que el layout servidor). */
export function useIsSuperAdminClient() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (!user) {
          if (!cancelled) {
            setIsAdmin(false);
            setLoaded(true);
          }
          return;
        }
        const adminProbe = await fetch(cedApiPath("support/admin/unread-count"), {
          credentials: "same-origin",
        });
        if (adminProbe.ok) {
          if (!cancelled) {
            setIsAdmin(true);
            setLoaded(true);
          }
          return;
        }
        const { data: profile } = await supabase
          .from("profiles")
          .select("role")
          .eq("id", user.id)
          .maybeSingle();
        const admin = isSuperAdmin(
          user.email,
          user.app_metadata?.role as string | undefined,
          profile?.role as string | undefined,
        );
        if (!cancelled) {
          setIsAdmin(admin);
          setLoaded(true);
        }
      } catch {
        if (!cancelled) {
          setIsAdmin(false);
          setLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { isAdmin, loaded };
}
