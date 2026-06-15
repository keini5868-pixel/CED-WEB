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
  created_at: string;
  updated_at: string;
};

export async function listConversations(): Promise<ConversationRow[]> {
  const res = await fetch(`${apiUrl()}/v1/conversations`, {
    headers: await authHeaders(),
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.conversations ?? [];
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
