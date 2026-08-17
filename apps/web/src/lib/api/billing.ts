import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

function billingErrorMessage(status: number, detail?: string): string {
  if (status === 401) return "Debes iniciar sesión para pagar.";
  if (status === 400 && detail) return detail;
  if (status === 503) {
    return detail || "Pagos no disponibles en este momento.";
  }
  return detail || "No se pudo iniciar el pago.";
}

export async function startSubscriptionCheckout(planId: string): Promise<string | null> {
  const res = await proxyFetch("billing/checkout/subscription", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_id: planId }),
  });
  const data = await parseApiJson<{ url?: string; detail?: string }>(res);
  if (!res.ok) {
    throw new Error(billingErrorMessage(res.status, data.detail));
  }
  return data.url ?? null;
}

export async function startRechargeCheckout(amountUsd: number): Promise<string | null> {
  const res = await proxyFetch("billing/checkout/recharge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount_usd: amountUsd }),
  });
  const data = await parseApiJson<{ url?: string; detail?: string }>(res);
  if (!res.ok) {
    throw new Error(billingErrorMessage(res.status, data.detail));
  }
  return data.url ?? null;
}

export async function openBillingPortal(): Promise<string | null> {
  const res = await proxyFetch("billing/portal", { method: "POST" });
  const data = await parseApiJson<{ url?: string; detail?: string }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "Portal no disponible.");
  }
  return data.url ?? null;
}

export async function continueWithFreeBasic(): Promise<void> {
  const res = await proxyFetch("billing/trial/continue-free", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
  if (!res.ok) {
    const data = await parseApiJson<{ detail?: string }>(res);
    throw new Error(data.detail || "No se pudo activar plan básico.");
  }
}
