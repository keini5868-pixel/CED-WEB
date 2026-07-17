"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RechargeModal } from "@/components/billing/RechargeModal";
import {
  VoiceLimitModal,
  voiceLimitReasonFromBalance,
} from "@/components/billing/VoiceLimitModal";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import { openBillingPortal } from "@/lib/api/billing";

export function HudUsageBar() {
  const { balance, loaded } = useUsageBalance();
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [limitModalOpen, setLimitModalOpen] = useState(false);
  const [portalBusy, setPortalBusy] = useState(false);
  const [rechargeReason, setRechargeReason] = useState<string | null>(null);

  useEffect(() => {
    const onRechargeNeeded = (e: Event) => {
      const detail = (e as CustomEvent<{ resource?: string; message?: string }>).detail;
      console.log("[WALLET] ced-recharge-needed", detail);
      setRechargeReason(detail?.message || null);
      setRechargeOpen(true);
    };
    window.addEventListener("ced-recharge-needed", onRechargeNeeded);
    return () => window.removeEventListener("ced-recharge-needed", onRechargeNeeded);
  }, []);
  const pct = Math.min(
    100,
    balance.plan > 0 ? (balance.used / balance.plan) * 100 : 0,
  );
  const remaining = Math.max(0, balance.plan - balance.used);
  const warn = pct >= 80 && pct < 95;
  const criticalWarn = pct >= 95 && !balance.blocked;
  const voiceLimit = voiceLimitReasonFromBalance(balance);
  const critical = Boolean(voiceLimit);
  const statusLabel = !loaded
    ? "Cargando…"
    : voiceLimit === "daily_limit"
      ? "Límite alcanzado"
      : voiceLimit === "trial_expired"
        ? "Prueba de voz terminada"
        : voiceLimit === "subscription"
          ? "Suscripción requerida"
          : voiceLimit === "no_voice"
            ? "Voz no incluida"
            : criticalWarn
              ? "Casi sin cupo"
              : warn
                ? "Uso elevado"
                : balance.plan > 0
                  ? "Plan activo"
                  : "Sin cupo voz";

  return (
    <div>
      <div className="ced-hud-text-primary flex flex-wrap items-center justify-between gap-2 font-medium">
        <span>
          USO VOZ HOY:{" "}
          {loaded
            ? `${balance.used.toFixed(1)} / ${balance.plan} min`
            : "— / — min"}
        </span>
        <span
          className={
            critical || criticalWarn
              ? "text-red-400"
              : warn
                ? "text-amber-400"
                : "ced-hud-text-accent"
          }
        >
          {statusLabel}
        </span>
      </div>
      <div className="mt-3 h-2.5 overflow-hidden rounded bg-[#1a1a1a]">
        <div
          className={`h-full transition-all duration-500 ${
            critical || criticalWarn
              ? "bg-red-500"
              : warn
                ? "bg-amber-400"
                : "bg-[#00e5ff]"
          }`}
          style={{ width: `${balance.plan > 0 ? pct : 0}%` }}
        />
      </div>
      <p className="ced-hud-text-muted mt-2 text-xs">
        Límite diario del asistente de voz · el chat de texto es independiente
      </p>

      {critical && loaded ? (
        <div className="mt-3 rounded border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-100">
          <p className="font-semibold text-red-200">
            {voiceLimit === "daily_limit"
              ? "Has alcanzado tu límite diario de voz"
              : voiceLimit === "trial_expired"
                ? "Tu prueba de 7 días de voz terminó"
                : "El asistente de voz requiere plan o recarga"}
          </p>
          <p className="mt-2 opacity-90">
            Adquiere un paquete para seguir disfrutando del servicio de voz, o recarga
            desde <strong className="text-white">$10</strong> para usar el asistente hoy.
            El chat y otras funciones gratuitas siguen disponibles.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <button
              type="button"
              onClick={() => setRechargeOpen(true)}
              className="rounded border border-cyan-400 bg-cyan-400/10 px-3 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-200 hover:bg-cyan-400/20"
            >
              RECARGAR DESDE $10
            </button>
            <Link
              href="/pricing"
              className="rounded border border-purple-400/60 bg-purple-500/10 px-3 py-2 text-center font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-purple-200 hover:bg-purple-500/20"
            >
              ADQUIRIR UN PLAN
            </Link>
            <button
              type="button"
              onClick={() => setLimitModalOpen(true)}
              className="text-[10px] text-cyan-400 underline hover:text-cyan-200"
            >
              Ver opciones
            </button>
          </div>
        </div>
      ) : null}

      {!critical && (warn || criticalWarn) && loaded ? (
        <div
          className={`mt-3 rounded border p-3 text-xs ${
            criticalWarn
              ? "border-red-500/40 bg-red-500/10 text-red-100"
              : "border-amber-500/40 bg-amber-500/10 text-amber-100"
          }`}
        >
          <p className="font-semibold">
            Te {remaining === 1 ? "queda" : "quedan"} {remaining.toFixed(0)} min de voz hoy
          </p>
          <p className="mt-1 opacity-90">
            Has usado el {pct.toFixed(0)}% de tu cupo diario.
          </p>
          <div className="mt-2 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setRechargeOpen(true)}
              className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 underline hover:text-cyan-200"
            >
              RECARGAR DESDE $10 →
            </button>
            <Link
              href="/pricing"
              className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 underline hover:text-cyan-200"
            >
              VER PLANES →
            </Link>
          </div>
        </div>
      ) : null}

      {balance.plan === 0 && !critical && loaded && (
        <p className="ced-hud-text-muted mt-2 text-xs">
          Sin minutos de voz en tu plan ·{" "}
          <Link href="/pricing" className="text-cyan-400 underline">
            Adquirir plan
          </Link>{" "}
          o{" "}
          <button
            type="button"
            onClick={() => setRechargeOpen(true)}
            className="text-cyan-400 underline"
          >
            recargar desde $10
          </button>
        </p>
      )}

      {balance.hasStripeCustomer && !critical && (
        <button
          type="button"
          disabled={portalBusy}
          onClick={() => {
            setPortalBusy(true);
            void openBillingPortal()
              .then((url) => {
                if (url) window.location.href = url;
              })
              .catch(() => {
                /* portal opcional */
              })
              .finally(() => setPortalBusy(false));
          }}
          className="ced-hud-text-muted mt-2 text-xs underline hover:text-cyan-300 disabled:opacity-50"
        >
          {portalBusy ? "Abriendo portal…" : "Gestionar suscripción en Stripe"}
        </button>
      )}

      <RechargeModal
        open={rechargeOpen}
        onClose={() => {
          setRechargeOpen(false);
          setRechargeReason(null);
        }}
        planMinutesDaily={balance.plan}
        contextMessage={rechargeReason}
      />
      <VoiceLimitModal
        open={limitModalOpen}
        onClose={() => setLimitModalOpen(false)}
        reason={voiceLimit ?? "daily_limit"}
        planMinutesDaily={balance.plan}
      />
    </div>
  );
}
