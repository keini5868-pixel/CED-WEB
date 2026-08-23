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

import { fetchUsageBalanceDetailed } from "@/lib/api/usage";

export type UsageBalanceState = {
  used: number;
  plan: number;
  percent: number;
  blocked: boolean;
  accessDenied: boolean;
  accessMessage: string | null;
  subscriptionStatus: string | null;
  hasStripeCustomer: boolean;
  /** true cuando el último fetch de balance falló (401/red) — no bloquear voz por esto */
  authFailed: boolean;
  planId: string | null;
  voiceStack: string | null;
  voiceTransport: string | null;
  voicePoolTrial: boolean;
  rechargeUsd: number;
  bonusMinutes: number;
  planMinutesDaily: number;
};

type UsageBalanceValue = {
  balance: UsageBalanceState;
  loaded: boolean;
  refresh: () => Promise<UsageBalanceState | null>;
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
  authFailed: false,
  planId: null,
  voiceStack: null,
  voiceTransport: null,
  voicePoolTrial: false,
  rechargeUsd: 0,
  bonusMinutes: 0,
  planMinutesDaily: 0,
};

const UsageBalanceContext = createContext<UsageBalanceValue | null>(null);

function useUsageBalancePoll(
  pollMs: number,
  enabled = true,
): UsageBalanceValue {
  const [balance, setBalance] = useState<UsageBalanceState>(EMPTY_BALANCE);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async (): Promise<UsageBalanceState | null> => {
    if (!enabled) return null;
    try {
      const result = await fetchUsageBalanceDetailed();
      if (!result.ok) {
        setBalance((prev) => ({
          ...prev,
          authFailed: result.error.toLowerCase().includes("sesión") ||
            result.error.includes("401"),
        }));
        return null;
      }
      const data = result.data as UsageBalance & {
        plan_minutes_daily?: number;
        used_minutes_today?: number;
        usage_percent?: number;
        access_denied?: boolean;
        access_message?: string | null;
        subscription_status?: string | null;
        plan_id?: string | null;
        voice_stack?: string | null;
        voice_transport?: string | null;
        voice_pool_trial?: boolean;
        recharge_balance_usd?: number;
        bonus_minutes_from_balance?: number;
        total_available_minutes?: number;
      };
      const planDaily = data.planMinutesDaily ?? data.plan_minutes_daily ?? 0;
      const total =
        data.total_available_minutes ??
        data.totalAvailableMinutes ??
        planDaily;
      const used = data.usedMinutesToday ?? data.used_minutes_today ?? 0;
      const next: UsageBalanceState = {
        used,
        plan: total,
        percent:
          data.usage_percent ?? (total ? (used / total) * 100 : 0),
        blocked: Boolean(data.blocked),
        accessDenied: Boolean(data.access_denied),
        accessMessage: data.access_message ?? null,
        subscriptionStatus:
          data.subscription_status ?? data.subscriptionStatus ?? null,
        hasStripeCustomer: Boolean(
          (data as { has_stripe_customer?: boolean }).has_stripe_customer,
        ),
        authFailed: false,
        planId: data.plan_id ?? data.planId ?? null,
        voiceStack: data.voice_stack ?? data.voiceStack ?? null,
        voiceTransport: data.voice_transport ?? data.voiceTransport ?? null,
        voicePoolTrial: Boolean(
          (data as { voice_pool_trial?: boolean }).voice_pool_trial,
        ),
        rechargeUsd: Number(data.recharge_balance_usd ?? 0),
        bonusMinutes: Number(data.bonus_minutes_from_balance ?? 0),
        planMinutesDaily: planDaily,
      };
      setBalance(next);
      setLoaded(true);
      return next;
    } catch {
      setBalance((prev) => ({ ...prev, authFailed: true }));
      return null;
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
