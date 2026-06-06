import type { UsageBalance } from "@ced/types";

import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

async function authHeaders(): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) throw new Error("Sin sesión");
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response | null> {
  try {
    return await fetch(`${apiUrl()}${path}`, init);
  } catch {
    return null;
  }
}

export type UsageBalanceApi = UsageBalance & {
  usage_percent?: number;
  plan_minutes_daily?: number;
  used_minutes_today?: number;
};

export async function fetchUsageBalance(): Promise<UsageBalanceApi | null> {
  const res = await apiFetch("/v1/usage/balance", {
    headers: await authHeaders(),
  });
  if (!res?.ok) return null;
  const raw = await res.json();
  return {
    ...raw,
    planMinutesDaily: raw.plan_minutes_daily ?? raw.planMinutesDaily,
    usedMinutesToday: raw.used_minutes_today ?? raw.usedMinutesToday,
  };
}

export async function startVoiceSession(): Promise<{
  session_id: string;
  conversation_id: string | null;
}> {
  const res = await apiFetch("/v1/usage/session/start", {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!res) {
    throw new Error(
      `No se pudo contactar la API en ${apiUrl()}. Ejecuta: pnpm dev:api`,
    );
  }
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
  const res = await apiFetch("/v1/usage/session/tick", {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ session_id: sessionId, seconds }),
  });
  if (!res?.ok) return null;
  return res.json();
}

export async function endVoiceSession(sessionId: string): Promise<void> {
  const res = await apiFetch("/v1/usage/session/end", {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res) return;
  if (res.status === 404) return;
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.warn(
      "[CED] session/end",
      (err as { detail?: string }).detail ?? res.status,
    );
  }
}
