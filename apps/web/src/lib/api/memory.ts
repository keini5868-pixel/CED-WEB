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

export async function saveMemory(
  key: string,
  content: string,
  category?: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const res = await authFetch("/v1/memory/save", {
      method: "POST",
      body: JSON.stringify({ key, content, category }),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
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
    const res = await authFetch("/v1/memory/search", {
      method: "POST",
      body: JSON.stringify({ query }),
    });
    const data = (await res.json()) as {
      ok?: boolean;
      error?: string;
      results?: Array<{ key: string; content: string }>;
    };
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || "Error al buscar memoria" };
    }
    return { ok: true, results: data.results || [] };
  } catch {
    return { ok: false, error: "No se pudo contactar la API" };
  }
}
