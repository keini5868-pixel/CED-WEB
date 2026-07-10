import type { ChatPdfAttachment } from "@/lib/api/chat";
import { proxyFetchAuthed, streamAuthHeaders } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type FinanceChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  pdf?: ChatPdfAttachment | null;
};

export type FinanceChatStatus = {
  configured: boolean;
  anthropic_configured?: boolean;
  google_configured?: boolean;
  llama_configured?: boolean;
  finance_db_ready?: boolean;
  finance_db_error?: string | null;
  model: string | null;
  stream_model?: string | null;
};

export type FinanceChatResult = {
  response: string;
  model: string;
  pdf?: ChatPdfAttachment | null;
};

export const FINANCE_DEFAULT_WELCOME =
  "Finanzas listas, señor. Dígame un gasto o ingreso para anotarlo, o pregúnteme cómo va este mes.";

const FINANCE_TIMEOUT_MS = 300_000;
// Corta el stream si no llegan datos en este tiempo (evita spinner infinito).
const FINANCE_STREAM_STALL_MS = 120_000;
const FINANCE_FALLBACK_MODEL = "ced-finance";

export async function fetchFinanceChatStatus(): Promise<FinanceChatStatus | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4_000);
    const res = await proxyFetchAuthed("finance/status", {
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return null;
    return (await res.json()) as FinanceChatStatus;
  } catch {
    return null;
  }
}

export async function sendFinanceChatMessageStream(
  message: string,
  history: FinanceChatMessage[],
  onToken: (chunk: string) => void,
  onStatus?: (text: string) => void,
): Promise<FinanceChatResult> {
  const controller = new AbortController();
  let stalled = false;
  let stallTimer: ReturnType<typeof setTimeout> | null = null;
  const armStallWatchdog = () => {
    if (stallTimer) clearTimeout(stallTimer);
    stallTimer = setTimeout(() => {
      stalled = true;
      controller.abort();
    }, FINANCE_STREAM_STALL_MS);
  };
  const clearStall = () => {
    if (stallTimer) clearTimeout(stallTimer);
  };
  const hardTimeout = setTimeout(() => controller.abort(), FINANCE_TIMEOUT_MS);

  armStallWatchdog();
  let res: Response;
  try {
    const headers = await streamAuthHeaders();
    res = await fetch("/api/ced/finance/chat/stream", {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify({
        message,
        history: history
          .filter((m) => {
            if (m.role !== "user" && m.role !== "assistant") return false;
            const c = m.content.trim().toLowerCase();
            if (m.role === "assistant" && c.includes("finanzas listas")) return false;
            return Boolean(m.content.trim());
          })
          .map((m) => ({ role: m.role, content: m.content })),
      }),
      signal: controller.signal,
    });
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
    return sendFinanceChatMessage(message, history);
  }

  if (!res.ok) {
    clearStall();
    clearTimeout(hardTimeout);
    const data = await parseApiJson<{ detail?: string }>(res);
    throw new Error(data.detail || "No se pudo procesar sus finanzas.");
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
  let finalPayload: FinanceChatResult | null = null;

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
      const statusText = String(parsed.text ?? "");
      if (statusText) onStatus?.(statusText);
      return;
    }
    if (eventName === "token") {
      const text = String(parsed.text ?? "");
      if (text) {
        streamedText += text;
        onToken(text);
      }
      return;
    }
    if (eventName === "done") {
      finalPayload = {
        response: String(parsed.response ?? ""),
        model: String(parsed.model ?? FINANCE_FALLBACK_MODEL),
        pdf: (parsed.pdf as ChatPdfAttachment | undefined) ?? null,
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
        model: FINANCE_FALLBACK_MODEL,
        pdf: null,
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

  const payload = finalPayload as FinanceChatResult | null;
  if (payload?.response?.trim()) {
    return payload;
  }
  if (streamedText.trim()) {
    return {
      response: streamedText.trim(),
      model: payload?.model ?? FINANCE_FALLBACK_MODEL,
      pdf: payload?.pdf ?? null,
    };
  }
  throw new Error("Respuesta incompleta de finanzas.");
}

export async function sendFinanceChatMessage(
  message: string,
  history: FinanceChatMessage[],
): Promise<FinanceChatResult> {
  const res = await proxyFetchAuthed("finance/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history: history.map((m) => ({ role: m.role, content: m.content })),
    }),
    signal: AbortSignal.timeout(FINANCE_TIMEOUT_MS),
  });
  const data = await parseApiJson<FinanceChatResult & { detail?: string }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo procesar sus finanzas.");
  }
  return {
    response: data.response ?? "",
    model: data.model ?? FINANCE_FALLBACK_MODEL,
    pdf: data.pdf ?? null,
  };
}
