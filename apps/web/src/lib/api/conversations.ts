import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

/** sessionStorage: el dashboard abre este hilo al cargar. */
export const CED_RESUME_CONVERSATION_KEY = "ced-resume-conversation";

export const VOICE_THREAD_RESUME_NOTE =
  "Esto fue una conversación de voz. Puedes seguir aquí por texto; el micrófono no se reabre solo.";

const LIST_CACHE_KEY = "ced-chat-list-cache";
const MSG_CACHE_PREFIX = "ced-chat-msgs:";

export type ConversationRow = {
  id: string;
  title: string;
  channel?: "voice" | "text";
  created_at: string;
  updated_at: string;
  preview?: string;
  message_count?: number;
  messages?: ConversationMessage[];
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
  includeMessages?: boolean;
};

export class ConversationsApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ConversationsApiError";
    this.status = status;
  }
}

let memList: ConversationRow[] | null = null;
const memMsgs = new Map<string, ConversationMessage[]>();

function stripMessages(row: ConversationRow): ConversationRow {
  const { messages: _ignored, ...rest } = row;
  return rest;
}

function readSession<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeSession(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota */
  }
}

export function peekCachedConversations(): ConversationRow[] | null {
  if (memList && memList.length > 0) return memList;
  const stored = readSession<ConversationRow[]>(LIST_CACHE_KEY);
  if (stored && Array.isArray(stored) && stored.length > 0) {
    memList = stored;
    return stored;
  }
  return memList;
}

export function peekCachedMessages(
  conversationId: string,
): ConversationMessage[] | null {
  const id = conversationId.trim();
  if (!id) return null;
  const hit = memMsgs.get(id);
  if (hit) return hit;
  const stored = readSession<ConversationMessage[]>(MSG_CACHE_PREFIX + id);
  if (stored && Array.isArray(stored)) {
    memMsgs.set(id, stored);
    return stored;
  }
  return null;
}

export function rememberConversationMessages(
  conversationId: string,
  messages: ConversationMessage[],
): void {
  const id = conversationId.trim();
  if (!id) return;
  const clipped = messages.slice(-80);
  memMsgs.set(id, clipped);
  writeSession(MSG_CACHE_PREFIX + id, clipped);
}

function rememberList(rows: ConversationRow[]): void {
  const slim = rows.map(stripMessages);
  memList = slim;
  writeSession(LIST_CACHE_KEY, slim);
  for (const row of rows) {
    if (row.messages && row.messages.length > 0) {
      rememberConversationMessages(row.id, row.messages);
    }
  }
}

export async function listConversations(
  options: ListConversationsOptions = {},
): Promise<ConversationRow[]> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.channel) params.set("channel", options.channel);
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.includeMessages) params.set("include_messages", "true");
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
  const rows = data.conversations ?? [];
  rememberList(rows);
  return rows;
}

export async function warmConversationCache(): Promise<void> {
  if (peekCachedConversations()?.length) {
    void listConversations({ limit: 40, includeMessages: true }).catch(() => {
      /* keep cache */
    });
    return;
  }
  try {
    await listConversations({ limit: 40, includeMessages: true });
  } catch {
    /* ignore */
  }
}

function emptyConversation(id: string): ConversationRow {
  return {
    id,
    title: "Conversación",
    created_at: "",
    updated_at: "",
  };
}

export async function createConversation(
  channel: "text" | "voice" = "text",
): Promise<ConversationRow | null> {
  try {
    const res = await proxyFetchAuthed(
      `conversations?channel=${encodeURIComponent(channel)}`,
      { method: "POST" },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { conversation?: ConversationRow };
    return data.conversation ?? null;
  } catch {
    return null;
  }
}

export async function getConversationMessages(
  conversationId: string,
): Promise<{ messages: ConversationMessage[]; conversation: ConversationRow }> {
  const id = conversationId.trim();
  const cached = peekCachedMessages(id);
  try {
    const res = await proxyFetchAuthed(
      `conversations/${encodeURIComponent(id)}/messages`,
    );
    if (!res.ok) {
      return {
        messages: cached ?? [],
        conversation: emptyConversation(id),
      };
    }
    const data = (await res.json()) as {
      messages?: ConversationMessage[];
      conversation?: ConversationRow;
    };
    const messages = data.messages ?? cached ?? [];
    rememberConversationMessages(id, messages);
    return {
      messages,
      conversation: data.conversation ?? emptyConversation(id),
    };
  } catch {
    return {
      messages: cached ?? [],
      conversation: emptyConversation(id),
    };
  }
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
