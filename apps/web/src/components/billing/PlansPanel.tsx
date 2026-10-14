"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import {
  FOUNDING_MEMBER_MAX_SLOTS,
  PUBLIC_PLANS,
  SENTINEL_PRIVACY_PRODUCT,
} from "@ced/types";

import { useUsageBalance } from "@/hooks/useUsageBalance";
import {
  startRechargeCheckout,
  startSentinelPrivacyCheckout,
  startSubscriptionCheckout,
} from "@/lib/api/billing";

type PlansPanelProps = {
  /** Compact layout for overlays; default is full dashboard section */
  compact?: boolean;
};

/**
 * In-app plans + recharge — used from /dashboard/plans and billing CTAs.
 * Does not leave the authenticated app shell for browsing; Stripe Checkout
 * still opens for payment.
 */
export function PlansPanel({ compact = false }: PlansPanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { balance, loaded } = useUsageBalance();

  const subscribe = useCallback(async (planId: string) => {
    setBusy(planId);
    setError(null);
    try {
      const url = await startSubscriptionCheckout(planId);
      if (url) window.location.href = url;
      else setError("Stripe no devolvió la página de pago.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al iniciar pago.");
    } finally {
      setBusy(null);
    }
  }, []);

  const recharge = useCallback(async (amount: number) => {
    setBusy(`recharge-${amount}`);
    setError(null);
    try {
      const url = await startRechargeCheckout(amount);
      if (url) window.location.href = url;
      else setError("No se pudo iniciar la recarga.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al iniciar recarga.");
    } finally {
      setBusy(null);
    }
  }, []);

  const paid = PUBLIC_PLANS.filter((p) => p.id !== "free_basic");
  const sentinel = SENTINEL_PRIVACY_PRODUCT;

  const subscribeSentinel = useCallback(async () => {
    setBusy(sentinel.id);
    setError(null);
    try {
      const url = await startSentinelPrivacyCheckout(sentinel.id);
      if (url) window.location.href = url;
      else setError("Stripe no devolvió la página de pago.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al iniciar pago.");
    } finally {
      setBusy(null);
    }
  }, [sentinel.id]);

  return (
    <div
      className={
        compact
          ? "max-h-[min(70dvh,calc(100dvh-8rem))] space-y-4 overflow-y-auto overscroll-y-contain pr-1 [-webkit-overflow-scrolling:touch]"
          : "mx-auto max-w-5xl space-y-6 px-4 py-6"
      }
    >
      <div>
        <h1 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wide text-cyan-200 sm:text-xl">
          Planes CED
        </h1>
        <p className="mt-1 text-sm text-cyan-100/70">
          Suscríbete o recarga saldo sin salir de la app. El chat de texto sigue
          disponible en plan Básico; la voz requiere plan o recarga.
        </p>
      </div>

      <section className="rounded border border-cyan-500/25 bg-black/40 p-4">
        <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
          RECARGAR SALDO
        </h2>
        <p className="mt-1 text-xs text-cyan-100/60">
          Desde $10 · crédito proporcional · no expira · desbloquea voz y extras
        </p>
        {loaded ? (
          <p className="mt-2 text-sm text-cyan-100">
            Saldo actual:{" "}
            <strong className="text-emerald-300">
              ${balance.rechargeUsd.toFixed(2)}
            </strong>
            {balance.bonusMinutes > 0
              ? ` · ≈ ${balance.bonusMinutes.toFixed(0)} min de voz extra`
              : ""}
            {" · "}
            Cupo: {balance.used.toFixed(1)} / {balance.plan.toFixed(0)} min
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {[10, 20, 40, 50, 100].map((amount) => (
            <button
              key={amount}
              type="button"
              disabled={busy !== null}
              onClick={() => void recharge(amount)}
              className="rounded border border-cyan-500/40 px-3 py-2 text-xs font-semibold text-cyan-200 hover:border-cyan-300 hover:bg-cyan-500/10 disabled:opacity-50"
            >
              {busy === `recharge-${amount}` ? "…" : `$${amount}`}
            </button>
          ))}
        </div>
      </section>

      <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
        SUSCRIPCIONES CED
      </h2>
      <div
        className={`grid gap-4 ${compact ? "sm:grid-cols-1" : "sm:grid-cols-2 lg:grid-cols-3"}`}
      >
        {paid.map((plan) => (
          <div
            key={plan.id}
            className={`rounded border p-4 ${
              plan.id === "founding"
                ? "border-amber-400/40 bg-amber-400/5"
                : "border-cyan-500/30 bg-black/40"
            }`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="font-[family-name:var(--font-orbitron)] text-base text-white">
                {plan.label}
              </h3>
              <p className="font-[family-name:var(--font-orbitron)] text-xl text-cyan-300">
                ${plan.priceUsd}
                <span className="text-xs text-cyan-600">/mes</span>
              </p>
            </div>
            {plan.id === "founding" ? (
              <p className="mt-1 text-[11px] text-amber-400">
                Cupos {FOUNDING_MEMBER_MAX_SLOTS} · precio bloqueado 6 meses
              </p>
            ) : plan.id === "cierre" ? (
              <p className="mt-1 text-[11px] text-cyan-500">
                Voz Jarvis · foco PM International
              </p>
            ) : null}
            <ul className="mt-3 space-y-1 text-xs text-cyan-100/75">
              {plan.highlights.slice(0, compact ? 4 : 8).map((h) => (
                <li key={h}>· {h}</li>
              ))}
            </ul>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void subscribe(plan.id)}
              className="mt-4 w-full rounded border border-cyan-400 py-2.5 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 hover:bg-cyan-400/10 disabled:opacity-50"
            >
              {busy === plan.id ? "REDIRIGIENDO A STRIPE…" : "SUSCRIBIRME"}
            </button>
          </div>
        ))}
      </div>

      <section id="sentinel-privacy-plan" className="scroll-mt-24 space-y-3">
        <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-violet-300">
          SENTINEL PRIVACY · PRODUCTO APARTE
        </h2>
        <p className="text-[11px] text-cyan-100/60">{sentinel.homeSubtitle}</p>
        <div className="relative rounded border border-violet-400/55 bg-gradient-to-br from-violet-950/45 to-black/50 p-4 ring-1 ring-violet-400/20 lg:max-w-xl">
          <span className="absolute -top-2.5 left-3 rounded bg-violet-500/35 px-2 py-0.5 font-[family-name:var(--font-orbitron)] text-[8px] font-bold tracking-wider text-violet-100">
            {sentinel.homeBadge}
          </span>
          <div className="flex items-baseline justify-between gap-2">
            <div>
              <p className="font-[family-name:var(--font-orbitron)] text-[9px] tracking-wider text-violet-400">
                PRODUCTO APARTE
              </p>
              <h3 className="font-[family-name:var(--font-orbitron)] text-base text-violet-50">
                {sentinel.label}
              </h3>
            </div>
            <p className="font-[family-name:var(--font-orbitron)] text-xl text-violet-200">
              ${sentinel.priceUsd}
              <span className="text-xs text-violet-500">/mes</span>
            </p>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-violet-200/75">
            {sentinel.homeSubtitle}
          </p>
          <ul className="mt-3 space-y-1 text-xs text-cyan-100/75">
            {sentinel.highlights.slice(0, compact ? 3 : 5).map((h) => (
              <li key={h}>· {h}</li>
            ))}
          </ul>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void subscribeSentinel()}
            className="mt-4 w-full rounded border border-violet-400/80 py-2.5 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-violet-100 hover:bg-violet-500/15 disabled:opacity-50"
          >
            {busy === sentinel.id ? "REDIRIGIENDO A STRIPE…" : "SUSCRIBIR SENTINEL"}
          </button>
        </div>
      </section>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <p className="text-center text-[11px] text-cyan-600">
        <Link href="/dashboard" className="underline hover:text-cyan-400">
          ← Volver al dashboard
        </Link>
        {" · "}
        Catálogo público también en{" "}
        <Link href="/pricing" className="underline hover:text-cyan-400">
          /pricing
        </Link>
      </p>
    </div>
  );
}
