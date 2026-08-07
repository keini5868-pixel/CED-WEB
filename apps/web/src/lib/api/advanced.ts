import type { ChatImageAttachment, ChatPdfAttachment } from "@/lib/api/chat";
import { proxyFetchAuthed, streamAuthHeaders } from "@/lib/api/ced-proxy";
import { coerceDisplayText, formatApiDetail } from "@/lib/display-text";
import { parseApiJson } from "@/lib/api/http";
import { appendStreamChunk } from "@/lib/stream-chunk";
export type AdvancedChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
  user_image_preview?: string | null;
};

export type AdvancedImageMode =
  | "analyze"
  | "variation"
  | "inspired"
  | "edit"
  | "publish";

export type AdvancedChatStatus = {
  configured: boolean;
  anthropic_configured?: boolean;
  google_configured?: boolean;
  model: string | null;
  stream_model?: string | null;
};

export type AdvancedChatResult = {
  response: string;
  model: string;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
};

/** Bienvenida instantánea — no esperar a /advanced/status. */
export const ADVANCED_DEFAULT_WELCOME =
  "Modo avanzado listo. ¿Qué analizamos, señor?";

const ADVANCED_TIMEOUT_MS = 300_000;
// Generación de imagen/PDF puede tardar >2 min — ampliar stall del stream.
const ADVANCED_STREAM_STALL_MS = 240_000;

export { ADVANCED_TIMEOUT_MS };

export async function fetchAdvancedChatStatus(): Promise<AdvancedChatStatus | null> {
  try {
    const res = await proxyFetchAuthed("advanced/status", {
      priority: "high",
    } as RequestInit);
    if (!res.ok) return null;
    return (await res.json()) as AdvancedChatStatus;
  } catch {
    return null;
  }
}

export async function sendAdvancedChatMessageStream(
  message: string,
  history: AdvancedChatMessage[],
  onToken: (chunk: string) => void,
  onStatus?: (text: string) => void,
): Promise<AdvancedChatResult> {
  const clientRequestId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `adv-${Date.now()}`;

  const controller = new AbortController();
  let stalled = false;
  let stallTimer: ReturnType<typeof setTimeout> | null = null;
  const armStallWatchdog = () => {
    if (stallTimer) clearTimeout(stallTimer);
    stallTimer = setTimeout(() => {
      stalled = true;
      controller.abort();
    }, ADVANCED_STREAM_STALL_MS);
  };
  const clearStall = () => {
    if (stallTimer) clearTimeout(stallTimer);
  };
  const hardTimeout = setTimeout(() => controller.abort(), ADVANCED_TIMEOUT_MS);

  armStallWatchdog();
  let res: Response;
  try {
    const headers = await streamAuthHeaders();
    res = await fetch("/api/ced/advanced/chat/stream", {
      method: "POST",
      credentials: "same-origin",
      headers,
      priority: "high",
      body: JSON.stringify({
        message,
        client_request_id: clientRequestId,
        history: history
          .filter((m) => {
            if (m.role !== "user" && m.role !== "assistant") return false;
            const c = m.content.trim().toLowerCase();
            if (m.role === "assistant" && c.includes("modo avanzado listo")) return false;
            if (m.role === "assistant" && c.includes("modo avanzado activo")) return false;
            return Boolean(m.content.trim());
          })
          .map((m) => ({ role: m.role, content: m.content })),
      }),
      signal: controller.signal,
    } as RequestInit);
  } catch (err) {
    clearStall();
    clearTimeout(hardTimeout);
    if (stalled) {
      throw new Error("El asistente tardó demasiado. Intenta de nuevo.");
    }
    throw err;
  }

  if (res.status === 404 || res.status === 405) {
    clearStall();
    clearTimeout(hardTimeout);
    return sendAdvancedChatMessage(message, history);
  }

  if (!res.ok) {
    clearStall();
    clearTimeout(hardTimeout);
    const data = await parseApiJson<{ detail?: unknown }>(res);
    throw new Error(
      formatApiDetail(data.detail, "No se pudo obtener respuesta de Claude."),
    );
  }

  if (!res.body) {
    clearStall();
    clearTimeout(hardTimeout);
    throw new Error("Stream no disponible.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamedText = "";
  let finalPayload: AdvancedChatResult | null = null;

  const parseEventBlock = (block: string) => {
    const lines = block.split("\n");
    let eventName = "message";
    let dataLine = "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLine += line.slice(5).trim();
      }
    }
    if (!dataLine) return;
    const parsed = JSON.parse(dataLine) as Record<string, unknown>;
    if (eventName === "status") {
      const statusText = coerceDisplayText(parsed.text).trim();
      if (statusText) onStatus?.(statusText);
      return;
    }
    if (eventName === "token") {
      const text = coerceDisplayText(parsed.text);
      if (text) {
        streamedText = appendStreamChunk(streamedText, text);
        onToken(text);
      }
      return;
    }
    if (eventName === "done") {
      finalPayload = {
        response: coerceDisplayText(parsed.response),
        model: coerceDisplayText(parsed.model) || "claude-sonnet-4-6",
        pdf: (parsed.pdf as ChatPdfAttachment | undefined) ?? null,
        image: (parsed.image as ChatImageAttachment | undefined) ?? null,
      };
    }
  };

  try {
    while (true) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      armStallWatchdog();
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        if (!part.trim()) continue;
        try {
          parseEventBlock(part);
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  } catch (err) {
    clearStall();
    clearTimeout(hardTimeout);
    if (stalled && streamedText.trim()) {
      return {
        response: streamedText.trim(),
        model: "claude-sonnet-4-6",
        pdf: null,
        image: null,
      };
    }
    if (stalled) {
      throw new Error("El asistente tardó demasiado. Intenta de nuevo.");
    }
    throw err;
  } finally {
    clearStall();
    clearTimeout(hardTimeout);
  }

  if (buffer.trim()) {
    try {
      parseEventBlock(buffer);
    } catch {
      /* ignore */
    }
  }

  const payload = finalPayload as AdvancedChatResult | null;
  if (payload) {
    const response = (payload.response?.trim() || streamedText.trim());
    if (response || payload.image?.url || payload.pdf?.file_id) {
      return {
        response: response || "Listo, señor.",
        model: payload.model ?? "claude-sonnet-4-6",
        pdf: payload.pdf ?? null,
        image: payload.image ?? null,
      };
    }
  }
  if (streamedText.trim()) {
    return {
      response: streamedText.trim(),
      model: payload?.model ?? "claude-sonnet-4-6",
      pdf: payload?.pdf ?? null,
      image: payload?.image ?? null,
    };
  }
  try {
    return await sendAdvancedChatMessage(message, history);
  } catch {
    throw new Error("Respuesta incompleta del modo avanzado.");
  }
}

/** Fallback sin streaming (PDF/imagen ya resueltos en servidor). */
export async function sendAdvancedChatMessage(
  message: string,
  history: AdvancedChatMessage[],
): Promise<AdvancedChatResult> {
  const res = await proxyFetchAuthed("advanced/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history: history.map((m) => ({ role: m.role, content: m.content })),
    }),
    signal: AbortSignal.timeout(ADVANCED_TIMEOUT_MS),
  });
  const data = await parseApiJson<AdvancedChatResult & { detail?: unknown }>(res);
  if (!res.ok) {
    throw new Error(
      formatApiDetail(data.detail, "No se pudo obtener respuesta de Claude."),
    );
  }
  return {
    response: coerceDisplayText(data.response),
    model: coerceDisplayText(data.model) || "claude-sonnet-4-6",
    pdf: data.pdf ?? null,
    image: data.image ?? null,
  };
}

/** Mensaje con imagen adjunta — análisis o generación con referencia. */
export async function sendAdvancedChatMessageWithImage(
  message: string,
  history: AdvancedChatMessage[],
  image: File,
  imageMode: AdvancedImageMode = "analyze",
): Promise<AdvancedChatResult> {
  const formData = new FormData();
  formData.append("content", message);
  formData.append("image_mode", imageMode);
  formData.append(
    "history_json",
    JSON.stringify(
      history
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content })),
    ),
  );
  formData.append("image", image, image.name || "attachment.jpg");

  const res = await proxyFetchAuthed("advanced/chat/with-image", {
    method: "POST",
    body: formData,
    signal: AbortSignal.timeout(ADVANCED_TIMEOUT_MS),
  });
  const data = await parseApiJson<AdvancedChatResult & { detail?: unknown }>(res);
  if (!res.ok) {
    throw new Error(
      formatApiDetail(
        data.detail,
        "No se pudo procesar la imagen en modo avanzado.",
      ),
    );
  }
  return {
    response: coerceDisplayText(data.response),
    model: coerceDisplayText(data.model) || "claude-sonnet-4-6",
    pdf: data.pdf ?? null,
    image: data.image ?? null,
  };
}
