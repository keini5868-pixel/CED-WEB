import { parseApiJson } from "@/lib/api/http";
import { proxyFetch } from "@/lib/api/ced-proxy";
import type { VoiceSessionPreferences } from "@ced/types";

export type RealtimeSessionResponse =
  | {
      ok: true;
      clientSecret: string;
      model: string;
      voiceName: string;
      systemInstruction: string;
      expiresInSeconds: number;
      transport?: string;
      sampleRate?: number;
      usagePercent?: number;
      warningLevel?: string | null;
    }
  | { ok: false; error: string; code?: string; usagePercent?: number; blocked?: boolean };

export type RealtimeCallResponse =
  | { ok: true; sdpAnswer: string }
  | { ok: false; error: string };

export async function negotiateRealtimeCall(
  sdpOffer: string,
  clientSecret: string,
): Promise<RealtimeCallResponse> {
  let response: Response;
  try {
    response = await proxyFetch("openai/realtime/calls", {
      method: "POST",
      headers: {
        "Content-Type": "application/sdp",
        "X-OpenAI-Ephemeral-Key": clientSecret,
      },
      body: sdpOffer,
    });
  } catch {
    return {
      ok: false,
      error: "No se pudo negociar WebRTC con la API.",
    };
  }

  if (!response.ok) {
    const data = (await parseApiJson<{ error?: string; detail?: string }>(response).catch(
      () => ({ error: `Error ${response.status}` }),
    )) as { error?: string; detail?: string };
    return {
      ok: false,
      error: data.detail || data.error || `Error ${response.status} en WebRTC`,
    };
  }

  const sdpAnswer = await response.text();
  if (!sdpAnswer.trim()) {
    return { ok: false, error: "OpenAI no devolvió SDP answer." };
  }
  return { ok: true, sdpAnswer };
}

export type RealtimeSessionOptions = Pick<
  VoiceSessionPreferences,
  "language" | "responseSpeed" | "voicePace" | "voiceWarmth" | "voiceEnergy" | "voiceProfile"
>;

export async function fetchRealtimeSession(
  voiceName?: string,
  options?: Partial<RealtimeSessionOptions>,
): Promise<RealtimeSessionResponse> {
  let response: Response;
  const body: Record<string, string | number> = {};
  if (voiceName) body.voiceName = voiceName;
  if (options?.language) body.language = options.language;
  if (options?.responseSpeed) body.responseSpeed = options.responseSpeed;
  if (options?.voicePace !== undefined) body.voicePace = options.voicePace;
  if (options?.voiceWarmth !== undefined) body.voiceWarmth = options.voiceWarmth;
  if (options?.voiceEnergy !== undefined) body.voiceEnergy = options.voiceEnergy;
  if (options?.voiceProfile) body.voiceProfile = options.voiceProfile;
  try {
    response = await proxyFetch("openai/realtime/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.keys(body).length ? body : {}),
    });
  } catch {
    return {
      ok: false,
      error: "No se pudo contactar la API. ¿Está activa en Railway?",
    };
  }

  const data = await parseApiJson<
    RealtimeSessionResponse & { detail?: string; blocked?: boolean }
  >(response);

  if (!response.ok || !data.ok) {
    return {
      ok: false,
      error:
        data.detail ||
        ("error" in data ? data.error : undefined) ||
        `Error ${response.status} al obtener sesión Realtime`,
      blocked: "blocked" in data ? data.blocked : undefined,
      usagePercent: "usagePercent" in data ? data.usagePercent : undefined,
    };
  }
  return data;
}

export type VoiceBriefResponse =
  | { ok: true; summary: string; kind: string; source?: string }
  | { ok: false; error: string; code?: string };

export async function fetchVoiceBrief(
  query: string,
  kind: "news" | "weather" | "general" = "news",
  timeoutMs = 24000,
): Promise<VoiceBriefResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await proxyFetch("openai/voice-brief", {
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

  const data = await parseApiJson<
    VoiceBriefResponse & { detail?: string; text?: string; summary?: string; error?: string }
  >(response);

  if (!response.ok) {
    return {
      ok: false,
      error: data.detail || ("error" in data ? data.error : undefined) || "Error al consultar",
    };
  }

  const summary = data.summary ?? data.text ?? "";
  if (summary) {
    return { ok: true, summary, kind, source: "source" in data ? data.source : undefined };
  }
  return {
    ok: false,
    error: ("error" in data ? data.error : undefined) || "Sin resultados",
  };
}

export async function fetchDeepAnalysis(
  prompt: string,
  timeoutMs = 30000,
): Promise<{ ok: true; result: string } | { ok: false; error: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await proxyFetch("openai/deep-analysis", {
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
    | { ok: true; result: string; text?: string }
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
  return { ok: true, result: data.result ?? data.text ?? "" };
}

export type GenerateImageResponse =
  | { ok: true; url: string; quality?: string }
  | { ok: false; error: string; code?: string };

export async function fetchGenerateImage(
  prompt: string,
  quality: "auto" | "standard" | "hd" = "auto",
  timeoutMs = 90000,
): Promise<GenerateImageResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await proxyFetch("openai/images/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, quality }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    const data = await parseApiJson<
      GenerateImageResponse & { detail?: string; url?: string }
    >(response);
    if (!response.ok || !data.ok) {
      return {
        ok: false,
        error:
          ("detail" in data ? data.detail : undefined) ||
          ("error" in data ? data.error : undefined) ||
          "No se pudo generar la imagen",
        code: "code" in data ? data.code : undefined,
      };
    }
    return { ok: true, url: data.url, quality: data.quality };
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, error: "La generación de imagen tardó demasiado", code: "timeout" };
    }
    return { ok: false, error: "No se pudo contactar la API" };
  }
}
