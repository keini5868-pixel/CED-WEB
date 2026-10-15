import { cedApiPath } from "@/lib/api/ced-proxy";
import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

function billingErrorMessage(status: number, detail?: string): string {
  if (status === 401) return "Debes iniciar sesión para pagar.";
  if (status === 405) {
    return "Abre ced-castillo.com/sentinel-privacy y pulsa SUSCRIBIR (no abras la URL de la API en el navegador).";
  }
  if (status === 400 && detail) return detail;
  if (status === 503) {
    return detail || "Pagos no disponibles en este momento.";
  }
  return detail || "No se pudo iniciar el pago.";
}

export type SentinelEntitlement = {
  active?: boolean;
  plan_id?: string | null;
  seals_per_month?: number;
  seals_used_in_period?: number;
  seals_remaining?: number;
  ced_included_cap?: number;
  sentinel_addon_cap?: number;
  status?: string;
};

export async function fetchSentinelSubscription(): Promise<{
  subscription: Record<string, unknown> | null;
  entitlement: SentinelEntitlement;
}> {
  const res = await proxyFetchAuthed("billing/sentinel-subscription", { method: "GET" });
  const data = await parseApiJson<{
    subscription?: Record<string, unknown> | null;
    entitlement?: SentinelEntitlement;
    detail?: string;
  }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo leer Sentinel.");
  }
  return {
    subscription: data.subscription ?? null,
    entitlement: data.entitlement ?? {},
  };
}

export async function startSentinelPrivacyCheckout(planId: string): Promise<string | null> {
  const res = await proxyFetchAuthed("billing/checkout/sentinel-privacy", {
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

export async function confirmCheckoutSession(sessionId: string): Promise<{
  ok: boolean;
  credited?: boolean;
  recharge_balance_usd?: number;
  plan_id?: string;
  detail?: string;
}> {
  const res = await proxyFetch("billing/confirm-checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await parseApiJson<{
    ok?: boolean;
    credited?: boolean;
    recharge_balance_usd?: number;
    plan_id?: string;
    detail?: string;
  }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo confirmar el pago.");
  }
  return {
    ok: Boolean(data.ok),
    credited: data.credited,
    recharge_balance_usd: data.recharge_balance_usd,
    plan_id: data.plan_id,
  };
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
