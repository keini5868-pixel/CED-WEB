import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type GoogleConnectionStatus = {
  connected: boolean;
  service: "calendar" | "gmail";
};

export type GoogleOAuthResult = {
  url: string | null;
  error?: string;
};

const proxyFetch = (path: string) =>
  fetch(cedApiPath(path), { credentials: "same-origin" });

export async function fetchGoogleCalendarStatus(): Promise<GoogleConnectionStatus | null> {
  try {
    const res = await proxyFetch("google/calendar/status");
    if (!res.ok) return null;
    return (await res.json()) as GoogleConnectionStatus;
  } catch {
    return null;
  }
}

export async function fetchGoogleGmailStatus(): Promise<GoogleConnectionStatus | null> {
  try {
    const res = await proxyFetch("google/gmail/status");
    if (!res.ok) return null;
    return (await res.json()) as GoogleConnectionStatus;
  } catch {
    return null;
  }
}

export async function fetchGoogleCalendarOAuthUrl(): Promise<GoogleOAuthResult> {
  try {
    const res = await proxyFetch("google/calendar/oauth/url");
    const data = await parseApiJson<{ url?: string; detail?: string }>(res);
    if (!res.ok) {
      return {
        url: null,
        error: data.detail || "No se pudo iniciar OAuth con Google Calendar.",
      };
    }
    return { url: data.url ?? null };
  } catch {
    return { url: null, error: "Error de red al contactar la API." };
  }
}

export async function fetchGoogleGmailOAuthUrl(): Promise<GoogleOAuthResult> {
  try {
    const res = await proxyFetch("google/gmail/oauth/url");
    const data = await parseApiJson<{ url?: string; detail?: string }>(res);
    if (!res.ok) {
      return {
        url: null,
        error: data.detail || "No se pudo iniciar OAuth con Gmail.",
      };
    }
    return { url: data.url ?? null };
  } catch {
    return { url: null, error: "Error de red al contactar la API." };
  }
}
