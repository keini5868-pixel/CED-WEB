import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type ChatMessage = {
  id?: string;
  role: "user" | "model" | "system";
  content: string;
  created_at?: string;
  pdf?: ChatPdfAttachment | null;
};

export type ChatPdfAttachment = {
  file_id: string;
  filename: string;
  title?: string;
  download_path?: string | null;
};

export type ChatStatus = {
  messages_used_today: number;
  messages_limit_daily: number | null;
  unlimited: boolean;
  remaining_today: number | null;
  blocked: boolean;
  trial_expired?: boolean;
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
): Promise<{
  conversation_id: string;
  reply: string;
  usage: ChatStatus;
  pdf?: ChatPdfAttachment | null;
}> {
  const res = await proxyFetch("chat/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      conversation_id: conversationId ?? undefined,
    }),
  });
  const data = await parseApiJson<{
    conversation_id?: string;
    reply?: string;
    usage?: ChatStatus;
    pdf?: ChatPdfAttachment;
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
  };
}
