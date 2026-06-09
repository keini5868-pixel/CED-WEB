"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

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

    if (billing === "success" && plan) {
      setMessage(`¡Plan ${plan.toUpperCase()} confirmado! Tu cuenta se actualiza en segundos.`);
    } else if (billing === "recharge_success" && amount) {
      setMessage(`Recarga de $${amount} confirmada. Minutos extra disponibles para voz.`);
    } else {
      setMessage(MESSAGES[billing] ?? null);
    }

    const url = new URL(window.location.href);
    url.searchParams.delete("billing");
    url.searchParams.delete("plan");
    url.searchParams.delete("amount");
    router.replace(`${url.pathname}${url.search}`, { scroll: false });
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
