"use client";

import { useCallback, useEffect, useState } from "react";

import type { UsageBalance } from "@ced/types";

import { fetchUsageBalance } from "@/lib/api/usage";

export function useUsageBalance(pollMs = 8000) {
  const [balance, setBalance] = useState<{
    used: number;
    plan: number;
    percent: number;
    blocked: boolean;
  }>({ used: 0, plan: 120, percent: 0, blocked: false });

  const refresh = useCallback(async () => {
    try {
      const data = (await fetchUsageBalance()) as
        | (UsageBalance & {
            plan_minutes_daily?: number;
            used_minutes_today?: number;
            usage_percent?: number;
          })
        | null;
      if (!data) return;
      const plan =
        data.planMinutesDaily ?? data.plan_minutes_daily ?? 120;
      const used =
        data.usedMinutesToday ?? data.used_minutes_today ?? 0;
      setBalance({
        used,
        plan,
        percent:
          (data as { usage_percent?: number }).usage_percent ??
          (plan ? (used / plan) * 100 : 0),
        blocked: Boolean(data.blocked),
      });
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  return { balance, refresh };
}
