/** Variables públicas y comprobaciones de configuración. */

/** API Railway producción — dominio con guion (servicio CED API). */
export const PRODUCTION_API_URL = "https://ced-web-production.up.railway.app";

/** Web Railway producción — URL pública del frontend (OAuth redirect). */
export const PRODUCTION_WEB_URL = "https://cedweb-production.up.railway.app";

/** Corrige typos habituales (cedweb / ced-api → ced-web-production). */
export function normalizeApiUrl(raw: string): string {
  const url = raw.trim().replace(/\/$/, "");
  if (!url) return url;
  if (
    url.includes("cedweb-production.up.railway.app") ||
    url.includes("ced-api-production.up.railway.app")
  ) {
    return PRODUCTION_API_URL;
  }
  return url;
}

/** Nunca devuelve 0.0.0.0 ni hosts internos de Railway. */
export function normalizeAppUrl(raw: string): string {
  const url = raw.trim().replace(/\/$/, "");
  if (!url) return "";
  if (
    url.includes("0.0.0.0") ||
    url.includes("127.0.0.1") ||
    url.includes("localhost:8080")
  ) {
    return PRODUCTION_WEB_URL;
  }
  if (
    url.includes("cedweb-production.up.railway.app") ||
    url.includes("ced-web-production.up.railway.app")
  ) {
    return PRODUCTION_WEB_URL;
  }
  return url;
}

export function isSupabaseConfigured(): boolean {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  return Boolean(url && key && !url.includes("TU_PROYECTO"));
}

/** URL pública del frontend — OAuth y callbacks de Supabase. */
export function appUrl(): string {
  const fromEnv = normalizeAppUrl(
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
      process.env.NEXT_PUBLIC_APP_URL?.trim() ||
      "",
  );
  if (fromEnv) return fromEnv;

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host && host !== "0.0.0.0" && host !== "127.0.0.1") {
      return `${window.location.protocol}//${window.location.host}`;
    }
  }

  return "http://localhost:3000";
}

export function apiUrl(): string {
  const serverOverride =
    typeof window === "undefined" ? process.env.CED_API_URL?.trim() : undefined;
  const raw =
    serverOverride ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "";

  if (raw) {
    return normalizeApiUrl(raw);
  }

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host.includes("railway.app") || host.includes("castillodigital.com")) {
      return PRODUCTION_API_URL;
    }
  }

  return "http://localhost:8000";
}

export function googleMapsKey(): string {
  return (
    process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY?.trim() ||
    process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY?.trim() ||
    ""
  );
}

/** OAuth Google — activo cuando Supabase está configurado (opt-out con false). */
export function isGoogleAuthEnabled(): boolean {
  if (process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "false") {
    return false;
  }
  return isSupabaseConfigured();
}

/** Soporte flotante — activo salvo NEXT_PUBLIC_SUPPORT_CHAT_ENABLED=false */
export function isSupportChatEnabled(): boolean {
  return process.env.NEXT_PUBLIC_SUPPORT_CHAT_ENABLED !== "false";
}
