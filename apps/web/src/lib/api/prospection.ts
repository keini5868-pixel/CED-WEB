import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new Error("Inicia sesión");
  }
  return fetch(`${apiUrl()}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string>),
    },
  });
}

export async function enableProspection(): Promise<
  { ok: true; enabled: boolean; spoken?: string } | { ok: false; error: string }
> {
  try {
    const res = await authFetch("/v1/prospection/enable", { method: "POST" });
    const data = (await res.json()) as {
      ok?: boolean;
      enabled?: boolean;
      error?: string;
      spoken?: string;
    };
    if (!res.ok || !data.ok) {
      return { ok: false, error: data.error || data.spoken || "No se pudo activar prospección" };
    }
    return { ok: true, enabled: Boolean(data.enabled), spoken: data.spoken };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function disableProspection(): Promise<
  { ok: true; enabled: boolean } | { ok: false; error: string }
> {
  try {
    const res = await authFetch("/v1/prospection/disable", { method: "POST" });
    const data = (await res.json()) as { ok?: boolean; enabled?: boolean; error?: string };
    if (!res.ok || !data.ok) {
      return { ok: false, error: data.error || "No se pudo desactivar prospección" };
    }
    return { ok: true, enabled: false };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function fetchProspectionReport(): Promise<
  { ok: true; spoken: string } | { ok: false; error: string }
> {
  try {
    const res = await authFetch("/v1/prospection/report");
    const data = (await res.json()) as { ok?: boolean; spoken?: string; error?: string };
    if (!res.ok || !data.ok) {
      return { ok: false, error: data.error || "Sin reporte" };
    }
    return { ok: true, spoken: data.spoken || "Sin leads hoy." };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function fetchProspectionStatus(): Promise<{
  enabled: boolean;
  leadsToday: number;
} | null> {
  try {
    const res = await authFetch("/v1/prospection/status");
    if (!res.ok) return null;
    const data = (await res.json()) as {
      enabled?: boolean;
      leads_today?: number;
    };
    return {
      enabled: Boolean(data.enabled),
      leadsToday: data.leads_today ?? 0,
    };
  } catch {
    return null;
  }
}
