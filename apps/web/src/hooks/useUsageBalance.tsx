"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import type { UsageBalance } from "@ced/types";

import { fetchUsageBalance } from "@/lib/api/usage";

export type UsageBalanceState = {
  used: number;
  plan: number;
  percent: number;
  blocked: boolean;
  accessDenied: boolean;
  accessMessage: string | null;
  subscriptionStatus: string | null;
  hasStripeCustomer: boolean;
};

type UsageBalanceValue = {
  balance: UsageBalanceState;
  loaded: boolean;
  refresh: () => Promise<void>;
};

const EMPTY_BALANCE: UsageBalanceState = {
  used: 0,
  plan: 0,
  percent: 0,
  blocked: false,
  accessDenied: false,
  accessMessage: null,
  subscriptionStatus: null,
  hasStripeCustomer: false,
};

const UsageBalanceContext = createContext<UsageBalanceValue | null>(null);

function useUsageBalancePoll(
  pollMs: number,
  enabled = true,
): UsageBalanceValue {
  const [balance, setBalance] = useState<UsageBalanceState>(EMPTY_BALANCE);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const data = (await fetchUsageBalance()) as
        | (UsageBalance & {
            plan_minutes_daily?: number;
            used_minutes_today?: number;
            usage_percent?: number;
            access_denied?: boolean;
            access_message?: string | null;
            subscription_status?: string | null;
          })
        | null;
      if (!data) return;
      const plan = data.planMinutesDaily ?? data.plan_minutes_daily ?? 0;
      const used = data.usedMinutesToday ?? data.used_minutes_today ?? 0;
      setBalance({
        used,
        plan,
        percent:
          (data as { usage_percent?: number }).usage_percent ??
          (plan ? (used / plan) * 100 : 0),
        blocked: Boolean(data.blocked),
        accessDenied: Boolean(
          (data as { access_denied?: boolean }).access_denied,
        ),
        accessMessage:
          (data as { access_message?: string | null }).access_message ?? null,
        subscriptionStatus:
          (data as { subscription_status?: string | null }).subscription_status ??
          data.subscriptionStatus ??
          null,
        hasStripeCustomer: Boolean(
          (data as { has_stripe_customer?: boolean }).has_stripe_customer,
        ),
      });
      setLoaded(true);
    } catch {
      /* ignore */
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const id = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(id);
  }, [enabled, refresh, pollMs]);

  return { balance, loaded, refresh };
}

/** Un solo poll compartido en el dashboard. */
export function UsageBalanceProvider({ children }: { children: ReactNode }) {
  const value = useUsageBalancePoll(8000);
  return (
    <UsageBalanceContext.Provider value={value}>
      {children}
    </UsageBalanceContext.Provider>
  );
}

/** Usa el contexto del dashboard si existe; si no, poll local (p. ej. /admin). */
export function useUsageBalance(pollMs = 8000) {
  const shared = useContext(UsageBalanceContext);
  const local = useUsageBalancePoll(pollMs, !shared);
  return shared ?? local;
}
