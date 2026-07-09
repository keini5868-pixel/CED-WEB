import { cedApiPath, streamAuthHeaders } from "@/lib/api/ced-proxy";
import { appendStreamChunk } from "@/lib/stream-chunk";
import { parseApiJson } from "@/lib/api/http";

const CHAT_TIMEOUT_MS = 90_000;
// Si el stream no envía datos en este tiempo, lo cortamos y mostramos error
// en vez de dejar el chat cargando para siempre.
const CHAT_STREAM_STALL_MS = 45_000;

/** Bienvenida instantánea en UI — no esperar a /chat/status. */
export const CHAT_DEFAULT_WELCOME =
  "Hola, soy CED. Escríbeme aquí, dicta con el micrófono o adjunta una imagen. " +
  "Puedo analizarla, generar variaciones o crear imágenes nuevas.";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), {
    credentials: "same-origin",
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(CHAT_TIMEOUT_MS),
  });

export type ChatPdfAttachment = {
  file_id: string;
  filename: string;
  title?: string;
  download_path?: string | null;
};

export type ChatImageAttachment = {
  url: string;
  prompt?: string;
  caption?: string;
  quality?: string;
};

export type ChatMessage = {
  id?: string;
  role: "user" | "model" | "system";
  content: string;
  created_at?: string;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
  /** Preview local de imagen adjunta por el usuario (solo UI) */
  user_image_preview?: string | null;
};

export type ChatStatus = {
  messages_used_today: number;
  messages_limit_daily: number | null;
  unlimited: boolean;
  remaining_today: number | null;
  blocked: boolean;
  trial_expired?: boolean;
  welcome_message?: string;
};

export async function fetchChatStatus(
  opts?: { welcome?: boolean },
): Promise<ChatStatus | null> {
  try {
    const qs = opts?.welcome ? "?welcome=true" : "";
    const res = await proxyFetch(`chat/status${qs}`);
    if (!res.ok) return null;
    return (await res.json()) as ChatStatus;
  } catch {
    return null;
  }
}

export async function fetchChatMessages(conversationId: string): Promise<ChatMessage[]> {
  const res = await proxyFetch(`chat/conversations/${conversationId}/messages`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.messages ?? [];
}

export async function sendChatMessage(
  content: string,
  conversationId?: string | null,
  image?: File | null,
  voicePublish?: boolean,
  onToken?: (chunk: string) => void,
): Promise<{
  conversation_id: string;
  reply: string;
  usage: ChatStatus;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
}> {
  if (image) {
    return sendChatMessageBlocking(
      content,
      conversationId,
      image,
      voicePublish,
    );
  }
  return sendChatMessageStream(content, conversationId, onToken ?? (() => {}));
}

async function sendChatMessageBlocking(
  content: string,
  conversationId?: string | null,
  image?: File | null,
  voicePublish?: boolean,
): Promise<{
  conversation_id: string;
  reply: string;
  usage: ChatStatus;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
}> {
  let res: Response;

  if (image) {
    const formData = new FormData();
    formData.append("content", content);
    if (conversationId) {
      formData.append("conversation_id", conversationId);
    }
    formData.append("image", image, image.name || "attachment.jpg");
    if (voicePublish) {
      formData.append("voice_publish", "true");
    }
    res = await proxyFetch("chat/send-with-image", {
      method: "POST",
      body: formData,
    });
  } else {
    res = await proxyFetch("chat/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        conversation_id: conversationId ?? undefined,
      }),
    });
  }

  const data = await parseApiJson<{
    conversation_id?: string;
    reply?: string;
    usage?: ChatStatus;
    pdf?: ChatPdfAttachment;
    image?: ChatImageAttachment;
    detail?: string;
  }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo enviar el mensaje.");
  }
  return {
    conversation_id: data.conversation_id!,
    reply: data.reply!,
    usage: data.usage!,
    pdf: data.pdf ?? null,
    image: data.image ?? null,
  };
}

type StreamDonePayload = {
  conversation_id: string;
  reply: string;
  usage: ChatStatus;
  pdf?: ChatPdfAttachment | null;
  image?: ChatImageAttachment | null;
};

/** Chat con streaming SSE — primer token en <1s. */
export async function sendChatMessageStream(
  content: string,
  conversationId: string | null | undefined,
  onToken: (chunk: string) => void,
): Promise<StreamDonePayload> {
  const controller = new AbortController();
  let stalled = false;
  let stallTimer: ReturnType<typeof setTimeout> | null = null;
  const armStallWatchdog = () => {
    if (stallTimer) clearTimeout(stallTimer);
    stallTimer = setTimeout(() => {
      stalled = true;
      controller.abort();
    }, CHAT_STREAM_STALL_MS);
  };

  armStallWatchdog();
  let res: Response;
  try {
    const headers = await streamAuthHeaders();
    res = await fetch("/api/ced/chat/send/stream", {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify({
        content,
        conversation_id: conversationId ?? undefined,
      }),
      signal: controller.signal,
    });
  } catch (err) {
    if (stallTimer) clearTimeout(stallTimer);
    if (stalled) {
      throw new Error(
        "El asistente tardó demasiado en responder. Intenta de nuevo en un momento.",
      );
    }
    throw err;
  }

  if (!res.ok) {
    if (stallTimer) clearTimeout(stallTimer);
    const data = await parseApiJson<{ detail?: string }>(res);
    throw new Error(data.detail || "No se pudo enviar el mensaje.");
  }

  if (!res.body) {
    if (stallTimer) clearTimeout(stallTimer);
    throw new Error("Stream no disponible.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamedText = "";
  let finalPayload: StreamDonePayload | null = null;

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
    if (eventName === "token") {
      const text = String(parsed.text ?? "");
      if (text) {
        streamedText = appendStreamChunk(streamedText, text);
        onToken(text);
      }
      return;
    }
    if (eventName === "done") {
      finalPayload = {
        conversation_id: String(parsed.conversation_id ?? ""),
        reply: String(parsed.reply ?? ""),
        usage: parsed.usage as ChatStatus,
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
          /* ignore malformed SSE chunk */
        }
      }
    }
  } catch (err) {
    if (stalled) {
      throw new Error(
        "El asistente tardó demasiado en responder. Intenta de nuevo en un momento.",
      );
    }
    throw err;
  } finally {
    if (stallTimer) clearTimeout(stallTimer);
  }

  if (buffer.trim()) {
    try {
      parseEventBlock(buffer);
    } catch {
      /* ignore trailing partial */
    }
  }

  // TypeScript no infiere asignaciones dentro del parser SSE.
  const payload = finalPayload as StreamDonePayload | null;
  if (payload?.conversation_id) {
    return payload;
  }
  if (streamedText.trim()) {
    return {
      conversation_id: payload?.conversation_id || conversationId || "",
      reply: streamedText.trim(),
      usage: payload?.usage ?? {
        messages_used_today: 0,
        messages_limit_daily: null,
        unlimited: false,
        remaining_today: null,
        blocked: false,
      },
      pdf: payload?.pdf ?? null,
      image: payload?.image ?? null,
    };
  }
  throw new Error("Respuesta incompleta del chat.");
}

export async function endChatConversation(conversationId: string): Promise<boolean> {
  try {
    const res = await proxyFetch(`chat/conversations/${conversationId}/end`, {
      method: "POST",
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { saved?: boolean };
    return Boolean(data.saved);
  } catch {
    return false;
  }
}

export async function transcribeChatAudio(audioBlob: Blob): Promise<string> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "recording.webm");
  const res = await proxyFetch("chat/transcribe", {
    method: "POST",
    body: formData,
  });
  const data = await parseApiJson<{ text?: string; detail?: string }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "Error transcribiendo audio.");
  }
  return (data.text || "").trim();
}
