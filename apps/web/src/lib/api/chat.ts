import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const CHAT_TIMEOUT_MS = 90_000;

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

export async function fetchChatStatus(): Promise<ChatStatus | null> {
  try {
    const res = await proxyFetch("chat/status");
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
