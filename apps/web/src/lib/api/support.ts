import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type SupportCategory = "bug" | "idea" | "question" | "other";
export type SupportStatus = "open" | "in_progress" | "resolved";

export type SupportConversation = {
  id: string;
  user_id: string;
  category: SupportCategory;
  status: SupportStatus;
  last_message_at?: string;
  unread_by_admin: boolean;
  unread_by_user: boolean;
  created_at?: string;
  user_email?: string;
  user_name?: string;
  last_message_preview?: string;
};

export type SupportMessage = {
  id: string;
  conversation_id: string;
  sender_type: "user" | "admin";
  sender_id: string;
  content: string;
  attachments: string[];
  created_at?: string;
};

export const SUPPORT_CATEGORY_LABELS: Record<
  SupportCategory,
  { label: string; emoji: string }
> = {
  bug: { label: "Reportar bug", emoji: "🐛" },
  idea: { label: "Sugerir idea", emoji: "💡" },
  question: { label: "Hacer pregunta", emoji: "❓" },
  other: { label: "Otro", emoji: "💬" },
};

/** Activo por defecto; la API puede desactivarlo en runtime. */
export async function fetchSupportChatEnabled(): Promise<boolean> {
  try {
    const res = await proxyFetch("support/status");
    if (!res.ok) return true;
    const data = await parseApiJson<{ enabled?: boolean }>(res);
    return data.enabled !== false;
  } catch {
    return true;
  }
}

export async function fetchUserSupportConversations(): Promise<SupportConversation[]> {
  const res = await proxyFetch("support/conversations");
  const data = await parseApiJson<{
    ok?: boolean;
    conversations?: SupportConversation[];
    detail?: string;
  }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo cargar conversaciones de soporte.");
  }
  return data.conversations ?? [];
}

export async function createSupportConversation(
  category: SupportCategory,
): Promise<SupportConversation> {
  const res = await proxyFetch("support/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category }),
  });
  const data = await parseApiJson<{
    ok?: boolean;
    conversation?: SupportConversation;
    detail?: string;
  }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo crear la conversación de soporte.");
  }
  if (!data.conversation) {
    throw new Error("No se pudo crear la conversación de soporte.");
  }
  return data.conversation;
}

export async function fetchSupportMessages(
  conversationId: string,
): Promise<SupportMessage[]> {
  const res = await proxyFetch(`support/conversations/${conversationId}/messages`);
  const data = await parseApiJson<{ ok?: boolean; messages?: SupportMessage[] }>(res);
  if (!res.ok) return [];
  return data.messages ?? [];
}

export async function sendSupportMessage(
  conversationId: string,
  content: string,
  attachments: string[] = [],
): Promise<SupportMessage | null> {
  const res = await proxyFetch(`support/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, attachments }),
  });
  const data = await parseApiJson<{ ok?: boolean; message?: SupportMessage; detail?: string }>(
    res,
  );
  if (!res.ok) throw new Error(data.detail || "No se pudo enviar el mensaje");
  return data.message ?? null;
}

export async function uploadSupportAttachment(
  conversationId: string,
  file: File,
): Promise<string | null> {
  const form = new FormData();
  form.append("file", file);
  const res = await proxyFetch(`support/conversations/${conversationId}/attachments`, {
    method: "POST",
    body: form,
  });
  const data = await parseApiJson<{ ok?: boolean; url?: string; detail?: string }>(res);
  if (!res.ok) throw new Error(data.detail || "No se pudo subir la imagen");
  return data.url ?? null;
}

export async function markSupportConversationRead(conversationId: string): Promise<void> {
  await proxyFetch(`support/conversations/${conversationId}/read`, { method: "PATCH" });
}

export async function fetchUserSupportUnreadCount(): Promise<number> {
  const res = await proxyFetch("support/user/unread-count");
  const data = await parseApiJson<{ count?: number }>(res);
  if (!res.ok) return 0;
  return data.count ?? 0;
}

export async function fetchAdminSupportConversations(filters?: {
  status?: SupportStatus;
  category?: SupportCategory;
  unread?: boolean;
}): Promise<SupportConversation[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.category) params.set("category", filters.category);
  if (filters?.unread) params.set("unread", "true");
  const qs = params.toString();
  const res = await proxyFetch(`support/admin/conversations${qs ? `?${qs}` : ""}`);
  const data = await parseApiJson<{ conversations?: SupportConversation[] }>(res);
  if (!res.ok) return [];
  return data.conversations ?? [];
}

export async function fetchAdminSupportUnreadCount(): Promise<number> {
  const res = await proxyFetch("support/admin/unread-count");
  const data = await parseApiJson<{ count?: number }>(res);
  if (!res.ok) return 0;
  return data.count ?? 0;
}

export async function adminUpdateSupportStatus(
  conversationId: string,
  status: SupportStatus,
): Promise<void> {
  const res = await proxyFetch(`support/admin/conversations/${conversationId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const data = await parseApiJson<{ detail?: string }>(res);
    throw new Error(data.detail || "No se pudo actualizar el estado");
  }
}

export async function adminSendSupportMessage(
  conversationId: string,
  content: string,
  attachments: string[] = [],
): Promise<SupportMessage | null> {
  return sendSupportMessage(conversationId, content, attachments);
}
