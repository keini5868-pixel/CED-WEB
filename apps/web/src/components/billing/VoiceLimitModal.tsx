"use client";

import Link from "next/link";
import { useState } from "react";

import { RechargeModal } from "@/components/billing/RechargeModal";
import { startSubscriptionCheckout } from "@/lib/api/billing";
import { PUBLIC_PLANS } from "@ced/types";

export type VoiceLimitReason =
  | "daily_limit"
  | "trial_daily_limit"
  | "voice_trial_limit"
  | "cierre_trial_limit"
  | "cierre_trial_expired"
  | "trial_expired"
  | "voice_trial_expired"
  | "no_voice"
  | "subscription";

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

  // Usuarios con plan pagado (daily_limit) solo necesitan recargar — ya están
  // suscritos. Usuarios en trial/sin voz/sin suscripción sí ven la opción de
  // suscribirse, porque todavía no pagan nada de forma recurrente.
  const isPaidPlanLimit = reason === "daily_limit";

  const title =
    reason === "daily_limit"
      ? "Límite diario de voz alcanzado"
      : reason === "trial_daily_limit" ||
          reason === "voice_trial_limit" ||
          reason === "cierre_trial_limit" ||
          reason === "voice_trial_expired"
        ? "Tu tiempo de prueba ha terminado"
        : reason === "cierre_trial_expired"
          ? "Tu prueba FitLine de 7 días terminó"
          : reason === "trial_expired"
            ? "Tu prueba de 7 días terminó"
            : reason === "no_voice"
              ? "Voz no incluida en tu plan"
              : "Suscripción requerida para voz";

  const trialVoiceDone =
    "Tu tiempo de prueba ha terminado. Recarga tiempo o elige un plan. " +
    "Imágenes, PDF y chat siguen disponibles mientras dure tu prueba de 7 días.";

  const body =
    reason === "daily_limit"
      ? "Has alcanzado el límite de tu plan. Recarga desde $10: el crédito es proporcional (voz, imágenes, búsquedas, PDF…) y no expira. El chat de texto sigue disponible."
      : reason === "trial_daily_limit" ||
          reason === "voice_trial_limit" ||
          reason === "cierre_trial_limit" ||
          reason === "voice_trial_expired"
        ? trialVoiceDone
        : reason === "cierre_trial_expired"
          ? "Tu prueba de 7 días terminó. Suscríbete a un plan para seguir con voz, o recarga desde $10."
          : reason === "trial_expired"
            ? "Tu prueba de 7 días finalizó. Adquiere un plan o recarga desde $10. El chat de texto sigue gratis en plan Básico."
            : reason === "no_voice"
              ? "Tu plan no incluye voz incluida. Recarga desde $10 para activar el asistente con crédito proporcional, o elige un plan. El chat de texto sigue disponible."
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
              {!isPaidPlanLimit && (
                <Link
                  href="/dashboard/plans"
                  onClick={onClose}
                  className="block w-full rounded-lg border border-purple-500/50 bg-purple-500/10 py-3 text-center font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-purple-200 transition hover:bg-purple-500/20"
                >
                  ADQUIRIR UN PLAN
                </Link>
              )}
            </div>

            {(reason === "trial_daily_limit" ||
              reason === "voice_trial_limit" ||
              reason === "cierre_trial_limit" ||
              reason === "cierre_trial_expired" ||
              reason === "voice_trial_expired" ||
              reason === "trial_expired" ||
              reason === "no_voice") && (
              <div className="mt-4 space-y-2 border-t border-cyan-500/20 pt-4">
                <p className="text-[10px] uppercase tracking-wider text-cyan-600">
                  Planes desde $22/mes
                </p>
                {PUBLIC_PLANS.filter((p) => p.id !== "free_basic")
                  .slice(0, 2)
                  .map((p) => (
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
              {reason === "voice_trial_limit" ||
              reason === "cierre_trial_limit" ||
              reason === "cierre_trial_expired" ||
              reason === "voice_trial_expired" ||
              reason === "trial_expired"
                ? "Los minutos de prueba de voz no se renuevan. El chat de texto no se bloquea."
                : "El cupo diario se renueva a medianoche. El chat de texto no se bloquea."}
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
  authFailed?: boolean;
  voicePoolTrial?: boolean;
}): VoiceLimitReason | null {
  if (balance.authFailed) return null;
  if (balance.accessDenied && balance.accessMessage === "cierre_trial_expired") {
    return "cierre_trial_expired";
  }
  if (balance.accessDenied && balance.accessMessage === "trial_expired") {
    return "trial_expired";
  }
  if (balance.accessMessage === "voice_trial_expired") {
    return "voice_trial_expired";
  }
  if (balance.accessDenied) return "subscription";
  if (balance.accessMessage === "free_basic" && balance.plan <= 0) {
    return "no_voice";
  }
  if (balance.blocked) {
    if (balance.accessMessage === "cierre_trial") return "cierre_trial_limit";
    if (balance.accessMessage === "trial") {
      if (balance.voicePoolTrial || balance.plan >= 15) return "voice_trial_limit";
      return "trial_daily_limit";
    }
    return "daily_limit";
  }
  return null;
}
