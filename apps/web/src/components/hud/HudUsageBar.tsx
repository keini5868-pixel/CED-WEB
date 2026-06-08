"use client";

import Link from "next/link";
import { useState } from "react";

import { useUsageBalance } from "@/hooks/useUsageBalance";
import { RechargeModal } from "@/components/billing/RechargeModal";

export function HudUsageBar() {
  const { balance, loaded } = useUsageBalance();
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const pct = Math.min(
    100,
    balance.plan > 0 ? (balance.used / balance.plan) * 100 : 0,
  );
  const warn = pct >= 80;
  const critical = balance.blocked || balance.accessDenied || pct >= 95;

  const statusLabel = !loaded
    ? "Cargando…"
    : balance.accessDenied
      ? "Suscripción requerida"
      : balance.blocked
        ? "Límite alcanado"
        : warn
          ? "Uso elevado"
          : balance.plan > 0
            ? "Plan activo"
            : "Sin cupo voz";

  return (
    <div>
      <div className="ced-hud-text-primary flex flex-wrap items-center justify-between gap-2 font-medium">
        <span>
          USO HOY:{" "}
          {loaded
            ? `${balance.used.toFixed(1)} / ${balance.plan} min`
            : "— / — min"}
        </span>
        <span
          className={
            critical
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
            critical ? "bg-red-500" : warn ? "bg-amber-400" : "bg-[#00e5ff]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="ced-hud-text-muted mt-2">
        Uso diario Gemini Live · {pct.toFixed(0)}% del cupo incluido
      </p>
      {(balance.accessDenied || balance.blocked || warn) && loaded && (
        <div
          className={`mt-3 rounded border p-3 text-xs ${
            balance.accessDenied || balance.blocked
              ? "border-red-500/40 bg-red-500/10 text-red-100"
              : "border-amber-500/40 bg-amber-500/10 text-amber-100"
          }`}
        >
          {balance.accessDenied ? (
            <>
              <p className="font-semibold">Acceso suspendido</p>
              <p className="mt-1 opacity-90">
                {balance.accessMessage === "trial_expired"
                  ? "Tu prueba terminó. Elige un plan para seguir con voz y chat."
                  : "Renueva tu plan en Precios para reactivar voz y chat."}
              </p>
              <Link
                href="/pricing"
                className="mt-2 inline-block font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 underline hover:text-cyan-200"
              >
                VER PLANES →
              </Link>
            </>
          ) : balance.blocked ? (
            <>
              <p className="font-semibold">Cupo diario agotado</p>
              <p className="mt-1 opacity-90">
                Recarga saldo para seguir con voz hoy, o vuelve mañana.
              </p>
            </>
          ) : (
            <>
              <p className="font-semibold">Te queda poco cupo hoy</p>
              <p className="mt-1 opacity-90">Considera una recarga antes de quedarte sin voz.</p>
            </>
          )}
          {balance.blocked && (
            <button
              type="button"
              onClick={() => setRechargeOpen(true)}
              className="mt-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 underline hover:text-cyan-200"
            >
              RECARGAR TIEMPO EXTRA →
            </button>
          )}
        </div>
      )}
      {balance.plan === 0 && (
        <p className="ced-hud-text-muted mt-2 text-xs">
          Plan Básico Gratis ·{" "}
          <Link href="/pricing" className="text-cyan-400 underline">
            Mejora aquí
          </Link>
        </p>
      )}
      <RechargeModal
        open={rechargeOpen}
        onClose={() => setRechargeOpen(false)}
        planMinutesDaily={balance.plan}
      />
    </div>
  );
}
