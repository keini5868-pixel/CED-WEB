"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { PUBLIC_PLANS } from "@ced/types";

import { trackPurchase } from "@/lib/ads/meta-pixel";
import { confirmCheckoutSession } from "@/lib/api/billing";

function purchaseValueUsd(plan: string | null, amount: string | null): number {
  const fromAmount = Number(amount);
  if (Number.isFinite(fromAmount) && fromAmount > 0) return fromAmount;
  const id = (plan || "").trim().toLowerCase();
  const listed = PUBLIC_PLANS.find((p) => p.id === id);
  return listed?.priceUsd ?? 0;
}

const MESSAGES: Record<string, string> = {
  success: "¡Pago confirmado! Tu plan se activará en unos segundos.",
  recharge_success: "¡Recarga exitosa! Ya tienes minutos extra de voz disponibles.",
  cancelled: "Pago cancelado. Puedes intentarlo de nuevo cuando quieras.",
  recharge_cancelled: "Recarga cancelada.",
};

export function BillingFeedback() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const billing = searchParams.get("billing");
    if (!billing) return;

    const plan = searchParams.get("plan");
    const amount = searchParams.get("amount");
    const sessionId = searchParams.get("session_id");

    let cancelled = false;

    const run = async () => {
      if (
        sessionId &&
        (billing === "recharge_success" || billing === "success")
      ) {
        try {
          const result = await confirmCheckoutSession(sessionId);
          if (cancelled) return;
          trackPurchase({
            value: purchaseValueUsd(plan, amount),
            planId: plan || (billing === "recharge_success" ? "recharge" : undefined),
            eventId: sessionId,
          });
          if (billing === "recharge_success") {
            const bal = result.recharge_balance_usd;
            setMessage(
              bal != null
                ? `Recarga confirmada. Saldo $${bal.toFixed(2)} disponible para voz.`
                : `Recarga de $${amount ?? ""} confirmada. Minutos extra disponibles.`,
            );
          } else if (plan) {
            setMessage(
              `¡Plan ${plan.toUpperCase()} activo! Tu cupo ya está en tu cuenta.`,
            );
          } else {
            setMessage(
              MESSAGES.success ??
                "¡Pago confirmado! Tu plan se activará en unos segundos.",
            );
          }
        } catch {
          if (cancelled) return;
          trackPurchase({
            value: purchaseValueUsd(plan, amount),
            planId: plan || (billing === "recharge_success" ? "recharge" : undefined),
            eventId: sessionId,
          });
          if (billing === "success" && plan) {
            setMessage(
              `¡Plan ${plan.toUpperCase()} confirmado! Si no ves el cupo en unos segundos, refresca.`,
            );
          } else if (billing === "recharge_success" && amount) {
            setMessage(
              `Pago de $${amount} recibido. Si no ves minutos, refresca o contacta soporte.`,
            );
          } else {
            setMessage(MESSAGES[billing] ?? null);
          }
        }
      } else if (billing === "success" && plan) {
        setMessage(
          `¡Plan ${plan.toUpperCase()} confirmado! Tu cuenta se actualiza en segundos.`,
        );
      } else if (billing === "recharge_success" && amount) {
        setMessage(
          `Recarga de $${amount} confirmada. Minutos extra disponibles para voz.`,
        );
      } else {
        setMessage(MESSAGES[billing] ?? null);
      }

      if (cancelled) return;
      const url = new URL(window.location.href);
      url.searchParams.delete("billing");
      url.searchParams.delete("plan");
      url.searchParams.delete("amount");
      url.searchParams.delete("session_id");
      router.replace(`${url.pathname}${url.search}`, { scroll: false });
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [router, searchParams]);

  if (!message) return null;

  const isError = message.includes("cancelad");

  return (
    <div
      className={`mb-4 rounded border px-4 py-3 text-sm ${
        isError
          ? "border-amber-500/40 bg-amber-500/10 text-amber-100"
          : "border-emerald-500/40 bg-emerald-500/10 text-emerald-100"
      }`}
      role="status"
    >
      {message}
    </div>
  );
}
