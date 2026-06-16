import type { UsageBalance } from "@ced/types";

import { cedApiPath } from "@/lib/api/ced-proxy";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type UsageBalanceApi = UsageBalance & {
  usage_percent?: number;
  plan_minutes_daily?: number;
  used_minutes_today?: number;
};

export type UsageBalanceResult =
  | { ok: true; data: UsageBalanceApi }
  | { ok: false; error: string };

export async function fetchUsageBalance(): Promise<UsageBalanceApi | null> {
  const result = await fetchUsageBalanceDetailed();
  return result.ok ? result.data : null;
}

export async function fetchUsageBalanceDetailed(): Promise<UsageBalanceResult> {
  try {
    const res = await fetch(cedApiPath("usage/balance"), {
      credentials: "same-origin",
    });
    const raw = await res.json().catch(() => ({} as Record<string, unknown>));
    if (!res.ok) {
      const detail =
        typeof raw.detail === "string"
          ? raw.detail
          : res.status === 502
            ? "No se pudo contactar la API. Revisa NEXT_PUBLIC_API_URL en Railway (servicio web) y redeploy."
            : `Error ${res.status} al consultar cupo de voz`;
      return { ok: false, error: detail };
    }
    return {
      ok: true,
      data: {
        ...(raw as UsageBalanceApi),
        planMinutesDaily:
          (raw as UsageBalanceApi).plan_minutes_daily ??
          (raw as UsageBalanceApi).planMinutesDaily,
        usedMinutesToday:
          (raw as UsageBalanceApi).used_minutes_today ??
          (raw as UsageBalanceApi).usedMinutesToday,
      },
    };
  } catch {
    return {
      ok: false,
      error:
        "Sin conexión con la API. Verifica NEXT_PUBLIC_API_URL=https://ced-web-production.up.railway.app y redeploy del web.",
    };
  }
}

export async function startVoiceSession(): Promise<{
  session_id: string;
  conversation_id: string | null;
}> {
  const res = await proxyFetch("usage/session/start", { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail || "Límite de voz alcanzado",
    );
  }
  return res.json();
}

export type VoiceSessionTick = {
  used_minutes_today: number;
  blocked: boolean;
  access_denied?: boolean;
  usage_percent: number;
  warning_level?: "warn" | "critical" | "blocked" | null;
  should_disconnect?: boolean;
};

/** Registra uso; null si la API no responde (no debe tumbar la voz). */
export async function tickVoiceSession(
  sessionId: string,
  seconds: number,
): Promise<VoiceSessionTick | null> {
  const res = await proxyFetch("usage/session/tick", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, seconds }),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function endVoiceSession(sessionId: string): Promise<void> {
  const res = await proxyFetch("usage/session/end", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (res.status === 404) return;
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.warn(
      "[CED] session/end",
      (err as { detail?: string }).detail ?? res.status,
    );
  }
}
