import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type MetaConnectionStatus = {
  connected: boolean;
  username?: string | null;
  followers_count?: number | null;
};

export type MetaOAuthResult = {
  url: string | null;
  error?: string;
};

const proxyFetch = (path: string) =>
  fetch(cedApiPath(path), { credentials: "same-origin" });

export async function fetchMetaStatus(): Promise<MetaConnectionStatus | null> {
  try {
    const res = await proxyFetch("meta/status");
    if (!res.ok) return null;
    return (await res.json()) as MetaConnectionStatus;
  } catch {
    return null;
  }
}

export async function fetchMetaOAuthUrl(): Promise<MetaOAuthResult> {
  try {
    const res = await proxyFetch("meta/oauth/url");
    const data = await parseApiJson<{ url?: string; detail?: string }>(res);
    if (!res.ok) {
      if (res.status === 401) {
        return {
          url: null,
          error:
            data.detail ||
            "Sesión inválida en la API. Revisa SUPABASE_* en Railway (servicio CED-WEB).",
        };
      }
      if (res.status === 503 && data.detail?.includes("META")) {
        return {
          url: null,
          error: "META no configurado en la API (META_APP_ID, META_APP_SECRET).",
        };
      }
      return {
        url: null,
        error: data.detail || "No se pudo iniciar OAuth con Meta.",
      };
    }
    return { url: data.url ?? null };
  } catch {
    return { url: null, error: "Error de red al contactar la API." };
  }
}
