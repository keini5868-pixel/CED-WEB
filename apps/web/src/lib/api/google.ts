import { createClient } from "@/lib/supabase/client";
import { apiUrl } from "@/lib/env";
import { parseApiJson } from "@/lib/api/http";

export type GoogleConnectionStatus = {
  connected: boolean;
  service: "calendar" | "gmail";
};

export type GoogleOAuthResult = {
  url: string | null;
  error?: string;
};

/** Base API — siempre dominio CED API (ced-web-production), nunca el host del web. */
export function googleCalendarLoginApiUrl(webOrigin?: string): string {
  const qs = webOrigin
    ? `?web_origin=${encodeURIComponent(webOrigin)}`
    : "";
  return `${apiUrl()}/auth/google/calendar/login${qs}`;
}

export function googleGmailLoginApiUrl(webOrigin?: string): string {
  const qs = webOrigin
    ? `?web_origin=${encodeURIComponent(webOrigin)}`
    : "";
  return `${apiUrl()}/auth/google/gmail/login${qs}`;
}

async function sessionAccessToken(): Promise<string | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

/** OAuth start — fetch directo al API (Bearer), no BFF same-origin. */
async function fetchGoogleOAuthUrlFromApi(
  path: "google/calendar/oauth/url" | "google/gmail/oauth/url",
): Promise<GoogleOAuthResult> {
  const token = await sessionAccessToken();
  if (!token) {
    return { url: null, error: "Inicia sesión para conectar Google." };
  }

  const webOrigin =
    typeof window !== "undefined" ? window.location.origin : "";
  const qs = webOrigin
    ? `?web_origin=${encodeURIComponent(webOrigin)}`
    : "";
  const target = `${apiUrl()}/v1/${path}${qs}`;

  try {
    const res = await fetch(target, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      cache: "no-store",
    });
    const data = await parseApiJson<{ url?: string; detail?: string }>(res);
    if (!res.ok) {
      return {
        url: null,
        error:
          data.detail ||
          `API OAuth ${res.status} — revisa NEXT_PUBLIC_API_URL=${apiUrl()}`,
      };
    }
    return { url: data.url ?? null };
  } catch {
    return {
      url: null,
      error: `No se pudo contactar la API en ${apiUrl()}.`,
    };
  }
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

export async function fetchGoogleCalendarOAuthUrl(): Promise<GoogleOAuthResult> {
  return fetchGoogleOAuthUrlFromApi("google/calendar/oauth/url");
}

export async function fetchGoogleGmailOAuthUrl(): Promise<GoogleOAuthResult> {
  return fetchGoogleOAuthUrlFromApi("google/gmail/oauth/url");
}
