import type { Session } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/client";
import { apiUrl, appUrl, PRODUCTION_WEB_URL } from "@/lib/env";
import { parseApiJson } from "@/lib/api/http";

export type GoogleConnectionStatus = {
  connected: boolean;
  service: "calendar" | "gmail";
  needs_reconnect?: boolean;
  hint?: string;
};

export type GoogleLinkType = "calendar" | "gmail";

const PENDING_LINK_KEY = "ced_pending_google_link";

const GOOGLE_SCOPES: Record<GoogleLinkType, string> = {
  calendar:
    "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly openid email profile",
  gmail:
    "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.modify",
};

async function sessionAccessToken(): Promise<string | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

function dashboardRedirectUrl(): string {
  const base = appUrl();
  if (base.includes("0.0.0.0") || base.includes("localhost:8080")) {
    return `${PRODUCTION_WEB_URL}/dashboard`;
  }
  return `${base}/dashboard`;
}

async function waitForProviderSession(): Promise<Session | null> {
  const supabase = createClient();
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (session?.provider_token) {
      return session;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session;
}

/** OAuth Google vía Supabase Auth (scopes adicionales sobre sesión existente). */
export async function connectGoogleViaSupabase(
  type: GoogleLinkType,
): Promise<{ error?: string }> {
  if (type === "calendar") {
    return connectGoogleCalendarViaApi();
  }

  const supabase = createClient();
  if (typeof window !== "undefined") {
    sessionStorage.setItem(PENDING_LINK_KEY, type);
  }

  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      scopes: GOOGLE_SCOPES[type],
      redirectTo: dashboardRedirectUrl(),
      queryParams: {
        access_type: "offline",
        prompt: "consent",
      },
    },
  });

  if (error) {
    if (typeof window !== "undefined") {
      sessionStorage.removeItem(PENDING_LINK_KEY);
    }
    return { error: error.message };
  }
  return {};
}

/** Calendar — OAuth directo vía API (scopes calendar.events garantizados). */
async function connectGoogleCalendarViaApi(): Promise<{ error?: string }> {
  const token = await sessionAccessToken();
  if (!token) {
    return { error: "Sin sesión activa." };
  }
  try {
    const res = await fetch(`${apiUrl()}/v1/google/calendar/oauth-url`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });
    const data = await parseApiJson<{ url?: string; detail?: string }>(res);
    if (!res.ok || !data.url) {
      return {
        error: data.detail || "No se pudo iniciar la conexión con Google Calendar.",
      };
    }
    if (typeof window !== "undefined") {
      window.location.href = data.url;
    }
    return {};
  } catch {
    return { error: "No se pudo contactar el servidor para conectar Calendar." };
  }
}

/** Tras el redirect OAuth, persiste provider_token en Supabase (API service_role). */
export async function saveGoogleProviderToken(
  type: GoogleLinkType,
): Promise<{ ok: boolean; error?: string }> {
  const session = await waitForProviderSession();
  if (!session?.access_token) {
    return { ok: false, error: "Sin sesión activa." };
  }

  const providerToken = session.provider_token;
  const providerRefreshToken = session.provider_refresh_token;
  if (!providerToken) {
    return {
      ok: false,
      error:
        "Sin provider_token en la sesión. Verifica scopes en Supabase → Auth → Google.",
    };
  }

  try {
    const res = await fetch("/api/ced/save-google-token", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({
        type,
        provider_token: providerToken,
        provider_refresh_token: providerRefreshToken ?? null,
      }),
    });
    const data = await parseApiJson<{ detail?: string; connected?: boolean }>(
      res,
    );
    if (!res.ok) {
      return {
        ok: false,
        error: data.detail || `Error al guardar token (${res.status}).`,
      };
    }
    return { ok: Boolean(data.connected ?? true) };
  } catch {
    return { ok: false, error: "No se pudo contactar el servidor." };
  }
}

export async function syncPendingGoogleProviderToken(): Promise<{
  type: GoogleLinkType | null;
  ok: boolean;
  error?: string;
}> {
  if (typeof window === "undefined") {
    return { type: null, ok: false };
  }

  const pending = sessionStorage.getItem(PENDING_LINK_KEY) as GoogleLinkType | null;
  if (!pending || (pending !== "calendar" && pending !== "gmail")) {
    return { type: null, ok: false };
  }

  const result = await saveGoogleProviderToken(pending);
  sessionStorage.removeItem(PENDING_LINK_KEY);
  return { type: pending, ...result };
}

export async function fetchGoogleCalendarStatus(): Promise<GoogleConnectionStatus | null> {
  const token = await sessionAccessToken();
  if (!token) return null;
  try {
    const res = await fetch(`${apiUrl()}/v1/google/calendar/status`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as GoogleConnectionStatus;
  } catch {
    return null;
  }
}

export async function fetchGoogleGmailStatus(): Promise<GoogleConnectionStatus | null> {
  const token = await sessionAccessToken();
  if (!token) return null;
  try {
    const res = await fetch(`${apiUrl()}/v1/google/gmail/status`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as GoogleConnectionStatus;
  } catch {
    return null;
  }
}
