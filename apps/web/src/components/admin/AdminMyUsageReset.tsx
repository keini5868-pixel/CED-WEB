"use client";

import { useCallback, useEffect, useState } from "react";

import { resetMyDailyUsage } from "@/lib/api/admin";
import { fetchUsageBalanceDetailed } from "@/lib/api/usage";

/** Renueva el límite diario de voz — solo visible en /admin para super admin. */
export function AdminMyUsageReset() {
  const [used, setUsed] = useState<number | null>(null);
  const [plan, setPlan] = useState<number | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    const result = await fetchUsageBalanceDetailed();
    if (!result.ok) {
      setError(result.error);
      setUsed(null);
      setPlan(null);
      return;
    }
    const balance = result.data;
    setUsed(balance.usedMinutesToday ?? balance.used_minutes_today ?? 0);
    setPlan(balance.planMinutesDaily ?? balance.plan_minutes_daily ?? 120);
    setBlocked(Boolean(balance.blocked));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleReset = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await resetMyDailyUsage();
      if (!result.ok) {
        setError(result.error || "Error al renovar");
        return;
      }
      setUsed(result.used_minutes_today ?? 0);
      setPlan(result.plan_minutes_daily ?? 120);
      setBlocked(Boolean(result.blocked));
      setMessage(
        `Cupo renovado. Se liberaron ${result.reset_minutes?.toFixed(1) ?? 0} min usados hoy.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al renovar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="ced-hud-text-body">
        Renueva tu cupo diario de voz Gemini Live. Solo afecta tu cuenta de
        admin — no modifica a otros usuarios.
      </p>

      <div className="rounded border border-cyan-500/30 bg-black/60 px-4 py-3">
        <p className="ced-hud-text-secondary text-xs uppercase tracking-widest">
          Uso hoy
        </p>
        <p className="mt-1 font-[family-name:var(--font-orbitron)] text-lg text-cyan-300">
          {used !== null && plan !== null
            ? `${used.toFixed(1)} / ${plan} min`
            : "—"}
          {blocked ? (
            <span className="ml-2 text-sm text-red-400">· Límite alcanzado</span>
          ) : null}
        </p>
        {used === null ? (
          <button
            type="button"
            onClick={() => void refresh()}
            className="mt-2 text-xs text-cyan-500 underline hover:text-cyan-300"
          >
            Ver uso actual
          </button>
        ) : null}
      </div>

      <button
        type="button"
        onClick={() => void handleReset()}
        disabled={loading}
        className="rounded border-2 border-amber-400/80 bg-amber-400/10 px-5 py-2.5 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-amber-200 transition hover:bg-amber-400/25 disabled:opacity-50"
      >
        {loading ? "RENOVANDO…" : "RENOVAR MI CUPO DIARIO"}
      </button>

      {message ? (
        <p className="text-sm text-emerald-400">{message}</p>
      ) : null}
      {error ? <p className="text-sm text-red-400">{error}</p> : null}
    </div>
  );
}
