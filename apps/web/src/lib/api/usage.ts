import type { UsageBalance } from "@ced/types";

import { cedApiPath } from "@/lib/api/ced-proxy";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type UsageBalanceApi = UsageBalance & {
  usage_percent?: number;
  plan_minutes_daily?: number;
  used_minutes_today?: number;
};

export async function fetchUsageBalance(): Promise<UsageBalanceApi | null> {
  try {
    const res = await fetch(cedApiPath("usage/balance"), {
      credentials: "same-origin",
    });
    if (!res.ok) return null;
    const raw = await res.json();
    return {
      ...raw,
      planMinutesDaily: raw.plan_minutes_daily ?? raw.planMinutesDaily,
      usedMinutesToday: raw.used_minutes_today ?? raw.usedMinutesToday,
    };
  } catch {
    return null;
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
  usage_percent: number;
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
