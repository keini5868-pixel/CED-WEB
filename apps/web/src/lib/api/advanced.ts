import type { ChatImageAttachment, ChatPdfAttachment } from "@/lib/api/chat";
import { authHeaders } from "@/lib/api/auth";
import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";
export type AdvancedChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
};

export type AdvancedChatStatus = {
  configured: boolean;
  model: string | null;
  stream_model?: string | null;
};

export type AdvancedChatResult = {
  response: string;
  model: string;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
};

const ADVANCED_TIMEOUT_MS = 300_000;

export async function fetchAdvancedChatStatus(): Promise<AdvancedChatStatus | null> {
  try {
    const res = await proxyFetchAuthed("advanced/status");
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
  let headers: HeadersInit = { "Content-Type": "application/json" };
  try {
    headers = { ...(await authHeaders()), ...headers };
  } catch {
    /* cookies-only fallback vía BFF */
  }

  const res = await fetch("/api/ced/advanced/chat/stream", {
    method: "POST",
    credentials: "same-origin",
    headers,
    body: JSON.stringify({
      message,
      history: history
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content })),
    }),
    signal: AbortSignal.timeout(ADVANCED_TIMEOUT_MS),
  });

  if (res.status === 404 || res.status === 405) {
    return sendAdvancedChatMessage(message, history);
  }

  if (!res.ok) {
    const data = await parseApiJson<{ detail?: string }>(res);
    throw new Error(data.detail || "No se pudo obtener respuesta de Claude.");
  }

  if (!res.body) {
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
        model: String(parsed.model ?? "claude-sonnet-4-6"),
        pdf: (parsed.pdf as ChatPdfAttachment | undefined) ?? null,
        image: (parsed.image as ChatImageAttachment | undefined) ?? null,
      };
    }
  };

  while (true) {
    const { value, done: streamDone } = await reader.read();
    if (streamDone) break;
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

  if (buffer.trim()) {
    try {
      parseEventBlock(buffer);
    } catch {
      /* ignore */
    }
  }

  const payload = finalPayload as AdvancedChatResult | null;
  if (payload?.response?.trim()) {
    return payload;
  }
  if (streamedText.trim()) {
    return {
      response: streamedText.trim(),
      model: payload?.model ?? "claude-sonnet-4-6",
      pdf: payload?.pdf ?? null,
      image: payload?.image ?? null,
    };
  }
  throw new Error("Respuesta incompleta del modo avanzado.");
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
  const data = await parseApiJson<AdvancedChatResult & { detail?: string }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo obtener respuesta de Claude.");
  }
  return {
    response: data.response ?? "",
    model: data.model ?? "claude-sonnet-4-6",
    pdf: data.pdf ?? null,
    image: data.image ?? null,
  };
}
