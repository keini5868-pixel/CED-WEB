"use client";

import { useCallback, useEffect, useState } from "react";

import {
  fetchSentinelSubscription,
  type SentinelEntitlement,
} from "@/lib/api/billing";
import { useIsSuperAdminClient } from "@/hooks/useIsSuperAdminClient";

export type SentinelTier = "full" | "lite" | "locked";

export type SentinelAccess = {
  loaded: boolean;
  tier: SentinelTier;
  entitlement: SentinelEntitlement;
  refresh: () => Promise<void>;
};

function tierFromEntitlement(
  ent: SentinelEntitlement,
  isAdmin: boolean,
): SentinelTier {
  if (isAdmin) return "full";
  const ced = Number(ent.ced_included_cap || 0);
  const addon = Number(ent.sentinel_addon_cap || 0);
  const cap = Number(ent.seals_per_month || 0);
  if (addon >= 200 || ced >= 200) return "full";
  if (ced > 0 || (ent.active && cap > 0)) return "lite";
  return "locked";
}

export function useSentinelAccess(): SentinelAccess {
  const { isAdmin, loaded: adminLoaded } = useIsSuperAdminClient();
  const [entitlement, setEntitlement] = useState<SentinelEntitlement>({});
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchSentinelSubscription();
      setEntitlement(data.entitlement || {});
    } catch {
      setEntitlement({});
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const tier = adminLoaded
    ? tierFromEntitlement(entitlement, isAdmin)
    : "locked";

  return {
    loaded: loaded && adminLoaded,
    tier: loaded && adminLoaded ? tier : "locked",
    entitlement,
    refresh,
  };
}
