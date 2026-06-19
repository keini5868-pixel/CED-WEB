"use client";

import { useEffect, useState } from "react";

import { isSuperAdmin } from "@/lib/auth/roles";
import { createClient } from "@/lib/supabase/client";

/** Detecta super admin en cliente (email, metadata y rol en profiles). */
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
