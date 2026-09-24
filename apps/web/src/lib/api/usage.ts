import type { UsageBalance } from "@ced/types";

import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

const proxyFetch = (path: string, init?: RequestInit) =>
  proxyFetchAuthed(path, init);

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
    const res = await proxyFetchAuthed("usage/balance");
    const raw = await res.json().catch(() => ({} as Record<string, unknown>));
    if (!res.ok) {
      const detail =
        typeof raw.detail === "string"
          ? raw.detail
          : res.status === 502
            ? "No se pudo contactar el servicio. Intente de nuevo."
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
        "Sin conexión con el servicio. Intente de nuevo en un momento.",
    };
  }
}

export async function startVoiceSession(conversationId?: string | null): Promise<{
  session_id: string;
  conversation_id: string | null;
  plan_id?: string | null;
  voice_stack?: string | null;
  voice_transport?: string | null;
}> {
  const res = await proxyFetch("usage/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: conversationId?.trim() || undefined,
    }),
  });
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
  plan_minutes_daily?: number;
  blocked: boolean;
  access_denied?: boolean;
  usage_percent: number;
  warning_level?: "warn" | "critical" | "blocked" | null;
  should_disconnect?: boolean;
  degraded?: boolean;
  disconnect_reason?: "quota" | "subscription" | null;
};

/** Mensaje explícito cuando el tick cierra la sesión por cupo o suscripción. */
export function voiceSessionDisconnectMessage(data: VoiceSessionTick): string | null {
  if (data.access_denied) {
    return "Tu suscripción no está activa. Renueva en Precios para usar la voz.";
  }
  if (data.blocked || data.should_disconnect) {
    const used = data.used_minutes_today ?? 0;
    const plan = data.plan_minutes_daily ?? 0;
    const pct = data.usage_percent ?? (plan ? (used / plan) * 100 : 100);
    const usedLabel = used.toFixed(1);
    return (
      `Límite diario de voz alcanzado (${usedLabel}/${plan || "?"} min, ${pct.toFixed(0)}%). ` +
      "La sesión se cerró por cupo — recarga en Precios o continúa mañana."
    );
  }
  return null;
}

export type VoiceSessionTickResult =
  | { ok: true; data: VoiceSessionTick }
  | { ok: false; authError: boolean; status: number };

/** Registra uso; fallo de auth/red no debe tumbar la voz activa. */
export async function tickVoiceSessionDetailed(
  sessionId: string,
  seconds: number,
): Promise<VoiceSessionTickResult> {
  const res = await proxyFetch("usage/session/tick", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, seconds }),
  });
  if (res.status === 401 || res.status === 403) {
    return { ok: false, authError: true, status: res.status };
  }
  if (!res.ok) {
    return { ok: false, authError: false, status: res.status };
  }
  const data = (await res.json()) as VoiceSessionTick;
  return { ok: true, data };
}

/** Registra uso; null si la API no responde (no debe tumbar la voz). */
export async function tickVoiceSession(
  sessionId: string,
  seconds: number,
): Promise<VoiceSessionTick | null> {
  const result = await tickVoiceSessionDetailed(sessionId, seconds);
  return result.ok ? result.data : null;
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
