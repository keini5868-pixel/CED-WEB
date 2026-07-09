import { cedApiPath, proxyFetchAuthed } from "@/lib/api/ced-proxy";

export type VisionSearchResult =
  | { ok: true; summary: string; query?: string; subject?: string }
  | { ok: false; error: string; code?: string };

async function proxyPost(path: string, body: object, timeoutMs = 28000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await proxyFetchAuthed(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchVisionWebSearch(
  imageDataUrl: string,
  question = "",
): Promise<VisionSearchResult> {
  try {
    const res = await proxyPost(
      "vision/search-web",
      {
        image: imageDataUrl,
        question,
      },
      17000,
    );
    const data = (await res.json()) as Record<string, unknown>;
    if (!res.ok || data.ok !== true) {
      return {
        ok: false,
        error: String(data.error || data.detail || "Error en búsqueda visual"),
        code: typeof data.code === "string" ? data.code : undefined,
      };
    }
    return {
      ok: true,
      summary: String(data.summary || ""),
      query: typeof data.query === "string" ? data.query : undefined,
      subject: typeof data.subject === "string" ? data.subject : undefined,
    };
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, error: "La búsqueda visual tardó demasiado", code: "timeout" };
    }
    return { ok: false, error: "No se pudo contactar la API" };
  }
}

export async function fetchVisionAnalyze(
  imageDataUrl: string,
  question = "",
): Promise<VisionSearchResult> {
  try {
    const res = await proxyPost(
      "vision/analyze",
      {
        image: imageDataUrl,
        question,
      },
      28000,
    );
    const data = (await res.json()) as Record<string, unknown>;
    if (!res.ok || data.ok !== true) {
      return { ok: false, error: String(data.error || "Error al analizar imagen") };
    }
    return {
      ok: true,
      summary: String(data.summary || ""),
      subject: typeof data.subject === "string" ? data.subject : undefined,
    };
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, error: "El análisis de cámara tardó demasiado", code: "timeout" };
    }
    return { ok: false, error: "No se pudo contactar la API" };
  }
}
