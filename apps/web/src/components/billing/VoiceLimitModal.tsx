"use client";

import Link from "next/link";
import { useState } from "react";

import { RechargeModal } from "@/components/billing/RechargeModal";
import { startSubscriptionCheckout } from "@/lib/api/billing";
import { PUBLIC_PLANS } from "@ced/types";

export type VoiceLimitReason = "daily_limit" | "trial_expired" | "no_voice" | "subscription";

type VoiceLimitModalProps = {
  open: boolean;
  onClose: () => void;
  reason: VoiceLimitReason;
  planMinutesDaily?: number;
};

export function VoiceLimitModal({
  open,
  onClose,
  reason,
  planMinutesDaily = 0,
}: VoiceLimitModalProps) {
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open && !rechargeOpen) return null;

  const title =
    reason === "daily_limit"
      ? "Límite diario de voz alcanzado"
      : reason === "trial_expired"
        ? "Tu prueba de voz terminó"
        : reason === "no_voice"
          ? "Voz no incluida en tu plan"
          : "Suscripción requerida para voz";

  const body =
    reason === "daily_limit"
      ? "Has alcanzado tu límite diario del asistente de voz. Recarga desde $10 para seguir hoy, o adquiere un plan con más minutos. El chat de texto sigue disponible sin costo."
      : reason === "trial_expired"
        ? "Los 7 días de prueba de voz finalizaron. Adquiere un plan o recarga desde $10 para usar el asistente de voz. El chat de texto sigue gratis en plan Básico."
        : reason === "no_voice"
          ? "Tu plan actual no incluye minutos de voz. Adquiere un paquete o recarga desde $10 para activar el asistente. El chat de texto sigue disponible."
          : "Renueva tu suscripción para reactivar el asistente de voz. El chat de texto sigue disponible.";

  const subscribe = async (planId: string) => {
    setBusy(planId);
    setError(null);
    try {
      const url = await startSubscriptionCheckout(planId);
      if (url) window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al suscribirse.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      {open ? (
        <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/75 p-4">
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-cyan-500/40 bg-[#0a0f14] p-6 shadow-2xl">
            <h2 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wider text-cyan-200">
              {title}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-cyan-100/85">{body}</p>

            <div className="mt-5 space-y-2">
              <button
                type="button"
                onClick={() => {
                  onClose();
                  setRechargeOpen(true);
                }}
                className="w-full rounded-lg border-2 border-cyan-400 bg-cyan-400/10 py-3 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-cyan-200 transition hover:bg-cyan-400/20"
              >
                RECARGAR DESDE $10
              </button>
              <Link
                href="/pricing"
                onClick={onClose}
                className="block w-full rounded-lg border border-purple-500/50 bg-purple-500/10 py-3 text-center font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-purple-200 transition hover:bg-purple-500/20"
              >
                ADQUIRIR UN PLAN
              </Link>
            </div>

            {(reason === "trial_expired" || reason === "no_voice") && (
              <div className="mt-4 space-y-2 border-t border-cyan-500/20 pt-4">
                <p className="text-[10px] uppercase tracking-wider text-cyan-600">
                  Planes desde $30/mes
                </p>
                {PUBLIC_PLANS.slice(0, 2).map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void subscribe(p.id)}
                    className="flex w-full items-center justify-between rounded border border-cyan-500/25 px-3 py-2 text-left text-sm text-cyan-100 hover:border-cyan-400/50 disabled:opacity-50"
                  >
                    <span>{p.label}</span>
                    <span className="text-cyan-400">${p.priceUsd}/mes</span>
                  </button>
                ))}
              </div>
            )}

            <p className="mt-4 text-center text-[11px] text-cyan-600">
              El cupo diario se renueva a medianoche. El chat de texto no se bloquea.
            </p>

            {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}

            <button
              type="button"
              onClick={onClose}
              className="mt-4 w-full rounded border border-cyan-800 py-2 text-xs text-cyan-500 hover:text-cyan-300"
            >
              Cerrar — seguir con chat gratis
            </button>
          </div>
        </div>
      ) : null}

      <RechargeModal
        open={rechargeOpen}
        onClose={() => setRechargeOpen(false)}
        planMinutesDaily={planMinutesDaily || 15}
      />
    </>
  );
}

export function voiceLimitReasonFromBalance(balance: {
  blocked: boolean;
  accessDenied: boolean;
  accessMessage: string | null;
  plan: number;
}): VoiceLimitReason | null {
  if (balance.accessDenied && balance.accessMessage === "trial_expired") {
    return "trial_expired";
  }
  if (balance.accessDenied) return "subscription";
  if (balance.accessMessage === "free_basic" && balance.plan <= 0) {
    return "no_voice";
  }
  if (balance.blocked) return "daily_limit";
  return null;
}
