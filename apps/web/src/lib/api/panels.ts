import type { HudState, PanelEvent } from "@ced/types";

import { HUD_BACKGROUND } from "@/lib/hud/hudBackgroundConfig";
import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

async function authHeaders(): Promise<HeadersInit | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) return null;
  return {
    Authorization: `Bearer ${session.access_token}`,
    Accept: "text/event-stream",
  };
}

export type VoiceSearchResponse =
  | { ok: true; summary: string; kind: string }
  | { ok: false; error: string };

/** Dispara búsqueda de paneles en background, retrasada para no afectar voz. */
export function schedulePanelSearch(
  query: string,
  kind: "news" | "weather" | "general" = "general",
  delayMs: number = HUD_BACKGROUND.panelSearchDelayMs,
): void {
  const q = query.trim();
  if (!q) return;
  window.setTimeout(() => {
    void triggerPanelSearch(q, kind);
  }, delayMs);
}

/** Dispara búsqueda de paneles en background (inmediata — preferir schedulePanelSearch). */
export async function triggerPanelSearch(
  query: string,
  kind: "news" | "weather" | "general" = "general",
): Promise<void> {
  const headers = await authHeaders();
  if (!headers) return;
  try {
    await fetch(`${apiUrl()}/v1/panels/search`, {
      method: "POST",
      headers: {
        ...headers,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ query, kind }),
    });
  } catch {
    /* paneles best-effort */
  }
}

/** Búsqueda voz + paneles en una llamada (legacy). */
export async function fetchVoiceSearchWithPanels(
  query: string,
  kind: "news" | "weather" | "general" = "general",
  timeoutMs = 16000,
): Promise<VoiceSearchResponse> {
  const headers = await authHeaders();
  if (!headers) {
    return { ok: false, error: "Inicia sesión para buscar" };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${apiUrl()}/v1/panels/voice-search`, {
      method: "POST",
      headers: {
        ...headers,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ query, kind }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    const data = (await res.json()) as VoiceSearchResponse & { detail?: string };
    if (!res.ok || !data.ok) {
      return {
        ok: false,
        error:
          data.detail ||
          ("error" in data ? data.error : undefined) ||
          "Error en búsqueda",
      };
    }
    return data;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, error: "La búsqueda tardó demasiado" };
    }
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

/** Conecta SSE de paneles; retorna función cleanup. */
export async function connectPanelStream(
  onEvent: (event: PanelEvent) => void,
  onError?: (err: Error) => void,
): Promise<() => void> {
  const headers = await authHeaders();
  if (!headers) {
    onError?.(new Error("Sin sesión"));
    return () => {};
  }

  const controller = new AbortController();

  void (async () => {
    try {
      const res = await fetch(`${apiUrl()}/v1/panels/stream`, {
        headers,
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`Stream ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk
            .split("\n")
            .map((l) => l.trim())
            .find((l) => l.startsWith("data:"));
          if (!line) continue;
          const json = line.slice(5).trim();
          if (!json) continue;
          try {
            const raw = JSON.parse(json) as { type?: string };
            if (raw.type === "ping") continue;
            onEvent(raw as PanelEvent);
          } catch {
            /* ignore */
          }
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      onError?.(err instanceof Error ? err : new Error("Stream error"));
    }
  })();

  return () => controller.abort();
}

/** @deprecated use @/lib/api/meta */
export { fetchMetaOAuthUrl } from "@/lib/api/meta";

export type HudPanelItem = {
  id: string;
  title: string;
  text: string;
  url?: string;
};

export type HudPanelsSnapshot = {
  hudState: HudState;
  lastQuery: string | null;
  global: HudPanelItem[];
  drones: HudPanelItem[];
  waves: HudPanelItem[];
  summary: string;
  streamConnected: boolean;
};

export const EMPTY_PANELS: HudPanelsSnapshot = {
  hudState: "idle",
  lastQuery: null,
  global: [],
  drones: [],
  waves: [],
  summary: "",
  streamConnected: false,
};
