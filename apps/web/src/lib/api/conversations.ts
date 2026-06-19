import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

async function authHeaders(): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) throw new Error("Sin sesión");
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

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

export async function listConversations(
  options: ListConversationsOptions = {},
): Promise<ConversationRow[]> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.channel) params.set("channel", options.channel);
  if (options.q?.trim()) params.set("q", options.q.trim());
  const qs = params.toString();
  const res = await fetch(`${apiUrl()}/v1/conversations${qs ? `?${qs}` : ""}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.conversations ?? [];
}

export async function getConversationMessages(
  conversationId: string,
): Promise<{ messages: ConversationMessage[]; conversation: ConversationRow }> {
  const res = await fetch(`${apiUrl()}/v1/conversations/${conversationId}/messages`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("No se pudo cargar la conversación.");
  return res.json();
}

export async function appendConversationMessage(
  conversationId: string,
  role: "user" | "model" | "system",
  content: string,
  sessionId?: string,
): Promise<void> {
  await fetch(`${apiUrl()}/v1/conversations/messages`, {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({
      conversation_id: conversationId,
      role,
      content,
      session_id: sessionId,
      channel: "voice",
    }),
  });
}
