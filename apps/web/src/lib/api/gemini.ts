import { parseApiJson } from "@/lib/api/http";
import { proxyFetch } from "@/lib/api/ced-proxy";

export type EphemeralTokenResponse =
  | {
      ok: true;
      token: string;
      model: string;
      voiceName: string;
      systemInstruction: string;
      expiresInSeconds: number;
    }
  | { ok: false; error: string };

export async function fetchEphemeralToken(
  voiceName?: string,
): Promise<EphemeralTokenResponse> {
  let response: Response;
  try {
    response = await proxyFetch("gemini/ephemeral-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(voiceName ? { voiceName } : {}),
    });
  } catch {
    return {
      ok: false,
      error: "No se pudo contactar la API. ¿Está activa en Railway?",
    };
  }

  const data = await parseApiJson<EphemeralTokenResponse & { detail?: string }>(
    response,
  );
  if (!response.ok) {
    const apiError =
      data.detail ||
      ("error" in data ? data.error : undefined) ||
      `Error ${response.status} al obtener token`;
    return { ok: false, error: apiError };
  }
  if (!data.ok) {
    const err = "error" in data ? data.error : "Token Gemini no disponible";
    return { ok: false, error: err };
  }
  return data;
}

export type VoiceBriefResponse =
  | { ok: true; summary: string; kind: string; source?: string }
  | { ok: false; error: string; code?: string };

export async function fetchDeepAnalysis(
  prompt: string,
  timeoutMs = 30000,
): Promise<{ ok: true; result: string } | { ok: false; error: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await proxyFetch("gemini/deep-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, error: "El sistema avanzado tardó demasiado" };
    }
    return { ok: false, error: "No se pudo contactar la API" };
  }
  clearTimeout(timer);

  const data = await parseApiJson<
    | { ok: true; result: string }
    | { ok: false; error: string; detail?: string }
  >(response);

  if (!response.ok || !data.ok) {
    return {
      ok: false,
      error:
        ("detail" in data ? data.detail : undefined) ||
        ("error" in data ? data.error : undefined) ||
        "Error en sistema avanzado",
    };
  }
  return data;
}

export async function fetchVoiceBrief(
  query: string,
  kind: "news" | "weather" | "general" = "news",
  timeoutMs = 24000,
): Promise<VoiceBriefResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await proxyFetch("gemini/voice-brief", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, kind }),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      return {
        ok: false,
        error: "La búsqueda tardó demasiado. Inténtelo de nuevo.",
        code: "client_timeout",
      };
    }
    return { ok: false, error: "No se pudo contactar la API" };
  }
  clearTimeout(timer);

  const data = await parseApiJson<VoiceBriefResponse & { detail?: string }>(
    response,
  );
  if (!response.ok || !data.ok) {
    return {
      ok: false,
      error:
        data.detail ||
        ("error" in data ? data.error : undefined) ||
        "Error al consultar noticias",
    };
  }
  return data;
}
