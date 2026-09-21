import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

/** sessionStorage: el dashboard abre este hilo al cargar. */
export const CED_RESUME_CONVERSATION_KEY = "ced-resume-conversation";

export type ConversationRow = {
  id: string;
  title: string;
  channel?: "voice" | "text";
  created_at: string;
  updated_at: string;
  preview?: string;
  message_count?: number;
};

export type ConversationMessage = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};

export type ListConversationsOptions = {
  limit?: number;
  channel?: "voice" | "text" | "";
  q?: string;
};

export class ConversationsApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ConversationsApiError";
    this.status = status;
  }
}

export async function listConversations(
  options: ListConversationsOptions = {},
): Promise<ConversationRow[]> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.channel) params.set("channel", options.channel);
  if (options.q?.trim()) params.set("q", options.q.trim());
  const qs = params.toString();
  const res = await proxyFetchAuthed(
    `conversations${qs ? `?${qs}` : ""}`,
  );
  if (!res.ok) {
    const raw = await res.json().catch(() => ({} as { detail?: string }));
    const detail =
      typeof raw.detail === "string"
        ? raw.detail
        : `No se pudo cargar el historial (HTTP ${res.status})`;
    throw new ConversationsApiError(detail, res.status);
  }
  const data = (await res.json()) as { conversations?: ConversationRow[] };
  return data.conversations ?? [];
}

export async function getConversationMessages(
  conversationId: string,
): Promise<{ messages: ConversationMessage[]; conversation: ConversationRow }> {
  const res = await proxyFetchAuthed(
    `conversations/${encodeURIComponent(conversationId)}/messages`,
  );
  if (!res.ok) {
    throw new ConversationsApiError(
      "No se pudo cargar la conversación.",
      res.status,
    );
  }
  return res.json();
}

export async function appendConversationMessage(
  conversationId: string,
  role: "user" | "model" | "system",
  content: string,
  sessionId?: string,
): Promise<{ ok: boolean; saved: boolean }> {
  const res = await proxyFetchAuthed("conversations/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: conversationId,
      role,
      content,
      session_id: sessionId,
      channel: "voice",
    }),
  });
  if (!res.ok) {
    return { ok: false, saved: false };
  }
  const data = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    saved?: boolean;
  };
  return { ok: data.ok !== false, saved: data.saved !== false };
}
