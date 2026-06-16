"use client";

import Link from "next/link";
import { useState } from "react";

import { useUsageBalance } from "@/hooks/useUsageBalance";
import { RechargeModal } from "@/components/billing/RechargeModal";
import { openBillingPortal } from "@/lib/api/billing";

export function HudUsageBar() {
  const { balance, loaded } = useUsageBalance();
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [portalBusy, setPortalBusy] = useState(false);
  const pct = Math.min(
    100,
    balance.plan > 0 ? (balance.used / balance.plan) * 100 : 0,
  );
  const remaining = Math.max(0, balance.plan - balance.used);
  const warn = pct >= 80 && pct < 95;
  const criticalWarn = pct >= 95 && !balance.blocked;
  const critical = balance.blocked || balance.accessDenied;
  const statusLabel = !loaded
    ? "Cargando…"
    : balance.accessDenied
      ? "Suscripción requerida"
      : balance.blocked
        ? "Límite alcanado"
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
          USO HOY:{" "}
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
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="ced-hud-text-muted mt-2">
        Uso diario de voz CED · {pct.toFixed(0)}% del cupo incluido
      </p>
      {(balance.accessDenied || balance.blocked || warn || criticalWarn) &&
        loaded && (
        <div
          className={`mt-3 rounded border p-3 text-xs ${
            balance.accessDenied || balance.blocked || criticalWarn
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
              <p className="font-semibold">Llegaste a tu cupo diario de voz</p>
              <p className="mt-1 opacity-90">
                Se renueva mañana a medianoche (UTC). Puedes recargar minutos extra
                o subir de plan.
              </p>
            </>
          ) : criticalWarn ? (
            <>
              <p className="font-semibold">
                Te {remaining === 1 ? "queda" : "quedan"}{" "}
                {remaining.toFixed(0)} min de voz hoy
              </p>
              <p className="mt-1 opacity-90">
                Estás al {pct.toFixed(0)}% del cupo. Considera una recarga antes de
                quedarte sin voz.
              </p>
            </>
          ) : (
            <>
              <p className="font-semibold">
                Te {remaining === 1 ? "queda" : "quedan"}{" "}
                {remaining.toFixed(0)} min de voz hoy
              </p>
              <p className="mt-1 opacity-90">
                Has usado el {pct.toFixed(0)}% de tu cupo diario.
              </p>
            </>
          )}
          {(balance.blocked || criticalWarn) && (
            <div className="mt-2 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => setRechargeOpen(true)}
                className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 underline hover:text-cyan-200"
              >
                RECARGAR TIEMPO EXTRA →
              </button>
              <Link
                href="/pricing"
                className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-300 underline hover:text-cyan-200"
              >
                SUBIR DE PLAN →
              </Link>
            </div>
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
      {balance.hasStripeCustomer && !balance.accessDenied && (
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
        onClose={() => setRechargeOpen(false)}
        planMinutesDaily={balance.plan}
      />
    </div>
  );
}
