"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";

import {
  SUPPORT_CATEGORY_LABELS,
  adminSendSupportMessage,
  adminUpdateSupportStatus,
  fetchAdminSupportConversations,
  fetchSupportMessages,
  markSupportConversationRead,
  type SupportCategory,
  type SupportConversation,
  type SupportMessage,
  type SupportStatus,
} from "@/lib/api/support";

type FilterKey = "unread" | SupportCategory | "all";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "unread", label: "Sin leer" },
  { key: "bug", label: "Bug" },
  { key: "idea", label: "Idea" },
  { key: "question", label: "Pregunta" },
  { key: "all", label: "Todos" },
];

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("es-MX", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function AdminSupportInbox() {
  const [filter, setFilter] = useState<FilterKey>("unread");
  const [conversations, setConversations] = useState<SupportConversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const selected = conversations.find((c) => c.id === selectedId) ?? null;

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchAdminSupportConversations({
        unread: filter === "unread" ? true : undefined,
        category: filter !== "all" && filter !== "unread" ? filter : undefined,
      });
      setConversations(items);
      if (selectedId && !items.some((c) => c.id === selectedId)) {
        setSelectedId(null);
        setMessages([]);
      }
    } catch {
      setError("No se pudo cargar conversaciones");
    } finally {
      setLoading(false);
    }
  }, [filter, selectedId]);

  useEffect(() => {
    void loadList();
    const t = window.setInterval(loadList, 30_000);
    return () => window.clearInterval(t);
  }, [loadList]);

  const openConversation = async (id: string) => {
    setSelectedId(id);
    setError(null);
    try {
      const msgs = await fetchSupportMessages(id);
      setMessages(msgs);
      await markSupportConversationRead(id);
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, unread_by_admin: false } : c)),
      );
    } catch {
      setError("No se pudieron cargar los mensajes");
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleReply = async () => {
    if (!selectedId || !reply.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      const msg = await adminSendSupportMessage(selectedId, reply.trim());
      if (msg) setMessages((prev) => [...prev, msg]);
      setReply("");
      void loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar");
    } finally {
      setSending(false);
    }
  };

  const setStatus = async (status: SupportStatus) => {
    if (!selectedId) return;
    try {
      await adminUpdateSupportStatus(selectedId, status);
      void loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al actualizar estado");
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-[480px] flex-col gap-3 p-4">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
              filter === f.key
                ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                : "border-cyan-500/20 text-cyan-500/80 hover:border-cyan-400/40"
            }`}
          >
            {f.label}
            {f.key === "unread"
              ? ` (${conversations.filter((c) => c.unread_by_admin).length || conversations.length})`
              : ""}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(260px,32%)_1fr]">
        <div className="overflow-y-auto rounded-xl border border-cyan-500/20 bg-black/30">
          {loading ? (
            <p className="p-4 text-sm text-cyan-500/70">Cargando…</p>
          ) : conversations.length === 0 ? (
            <p className="p-4 text-sm text-cyan-500/70">Sin conversaciones</p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => void openConversation(c.id)}
                className={`w-full border-b border-cyan-500/10 px-4 py-3 text-left transition hover:bg-cyan-500/5 ${
                  selectedId === c.id ? "bg-cyan-500/10" : ""
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-cyan-100">
                      {c.user_name || c.user_email || "Usuario"}
                    </p>
                    <p className="text-[11px] text-cyan-500/70">
                      {SUPPORT_CATEGORY_LABELS[c.category].emoji}{" "}
                      {SUPPORT_CATEGORY_LABELS[c.category].label}
                    </p>
                  </div>
                  {c.unread_by_admin ? (
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-red-500" />
                  ) : null}
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-cyan-400/80">
                  {c.last_message_preview || "Sin mensajes"}
                </p>
                <p className="mt-1 text-[10px] text-cyan-600">{formatTime(c.last_message_at)}</p>
              </button>
            ))
          )}
        </div>

        <div className="flex min-h-0 flex-col rounded-xl border border-cyan-500/20 bg-black/30">
          {!selected ? (
            <p className="flex flex-1 items-center justify-center text-sm text-cyan-500/60">
              Selecciona una conversación
            </p>
          ) : (
            <>
              <header className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/15 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-cyan-100">
                    {selected.user_name || selected.user_email}
                  </p>
                  <p className="text-xs text-cyan-500/70">{selected.user_email}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void setStatus("in_progress")}
                    className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] text-cyan-300 hover:bg-cyan-500/10"
                  >
                    En progreso
                  </button>
                  <button
                    type="button"
                    onClick={() => void setStatus("resolved")}
                    className="rounded border border-emerald-500/40 px-2 py-1 text-[10px] text-emerald-300 hover:bg-emerald-500/10"
                  >
                    Marcar resuelto
                  </button>
                </div>
              </header>

              <div className="flex-1 space-y-3 overflow-y-auto p-4">
                {messages.map((m) => {
                  const isAdmin = m.sender_type === "admin";
                  return (
                    <div
                      key={m.id}
                      className={`flex ${isAdmin ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                          isAdmin
                            ? "rounded-br-md bg-gradient-to-br from-purple-600 to-blue-600 text-white"
                            : "rounded-bl-md border border-cyan-500/20 bg-[#111827] text-cyan-50"
                        }`}
                      >
                        {m.content ? (
                          <p className="whitespace-pre-wrap break-words">{m.content}</p>
                        ) : null}
                        {m.attachments?.map((url) => (
                          <a key={url} href={url} target="_blank" rel="noreferrer" className="mt-2 block">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={url}
                              alt="Adjunto"
                              className="max-h-48 rounded-lg border border-white/10 object-cover"
                            />
                          </a>
                        ))}
                        <p
                          className={`mt-1 text-[10px] ${isAdmin ? "text-white/70" : "text-cyan-500/60"}`}
                        >
                          {formatTime(m.created_at)}
                        </p>
                      </div>
                    </div>
                  );
                })}
                <div ref={bottomRef} />
              </div>

              <footer className="border-t border-cyan-500/15 p-3">
                {error ? <p className="mb-2 text-xs text-red-400">{error}</p> : null}
                <div className="flex gap-2">
                  <textarea
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    rows={2}
                    placeholder="Responder al usuario…"
                    className="min-h-[44px] flex-1 resize-none rounded-lg border border-cyan-500/25 bg-black/40 px-3 py-2 text-sm text-cyan-50 outline-none focus:border-cyan-400/50"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void handleReply();
                      }
                    }}
                  />
                  <button
                    type="button"
                    disabled={sending || !reply.trim()}
                    onClick={() => void handleReply()}
                    className="self-end rounded-lg bg-gradient-to-br from-purple-600 to-blue-600 p-2 text-white disabled:opacity-50"
                  >
                    <Send size={18} />
                  </button>
                </div>
              </footer>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
