import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

async function proxyMemoryFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(cedApiPath(path), { credentials: "same-origin", ...init });
}

export async function saveMemory(
  key: string,
  content: string,
  category?: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const res = await proxyMemoryFetch("memory/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, content, category }),
    });
    const data = await parseApiJson<{ ok?: boolean; error?: string }>(res);
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || "Error al guardar memoria" };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function searchMemory(
  query: string,
): Promise<
  | { ok: true; results: Array<{ key: string; content: string }> }
  | { ok: false; error: string }
> {
  try {
    const res = await proxyMemoryFetch("memory/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await parseApiJson<{
      ok?: boolean;
      error?: string;
      results?: Array<{ key: string; content: string }>;
    }>(res);
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || "Error al buscar memoria" };
    }
    return { ok: true, results: data.results || [] };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function recallPreviousConversations(
  query: string,
  daysBack = 30,
): Promise<
  | { ok: true; spoken: string; results?: unknown[] }
  | { ok: false; error: string }
> {
  try {
    const res = await proxyMemoryFetch("memory/recall-conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, days_back: daysBack }),
    });
    const data = await parseApiJson<{
      ok?: boolean;
      error?: string;
      spoken?: string;
      results?: unknown[];
    }>(res);
    if (!res.ok || !data.ok) {
      return {
        ok: false,
        error: data.error || "No se pudo buscar conversaciones previas",
      };
    }
    return {
      ok: true,
      spoken: data.spoken || "Encontré contexto previo.",
      results: data.results,
    };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function saveLongTermMemory(
  category: string,
  key: string,
  value: string,
  importance = 5,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const res = await proxyMemoryFetch("memory/long-term/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category,
        key,
        value,
        importance,
      }),
    });
    const data = await parseApiJson<{ ok?: boolean; error?: string }>(res);
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || "Error al guardar memoria" };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}
