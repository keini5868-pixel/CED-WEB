"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ImagePlus, Send, X } from "lucide-react";

import {
  SUPPORT_CATEGORY_LABELS,
  createSupportConversation,
  fetchSupportMessages,
  fetchUserSupportConversations,
  markSupportConversationRead,
  sendSupportMessage,
  uploadSupportAttachment,
  type SupportCategory,
  type SupportConversation,
  type SupportMessage,
} from "@/lib/api/support";

type Props = {
  onClose: () => void;
  onMessageRead: () => void;
};

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

function CategoryPicker({
  sending,
  onPick,
}: {
  sending: boolean;
  onPick: (category: SupportCategory) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-cyan-100">¿En qué podemos ayudarte?</p>
      <p className="text-[11px] text-cyan-500/70">
        Elige una categoría para abrir un reporte nuevo.
      </p>
      {(Object.keys(SUPPORT_CATEGORY_LABELS) as SupportCategory[]).map((key) => {
        const { label, emoji } = SUPPORT_CATEGORY_LABELS[key];
        return (
          <button
            key={key}
            type="button"
            disabled={sending}
            onClick={() => onPick(key)}
            className="flex w-full items-center gap-3 rounded-xl border border-cyan-500/25 bg-cyan-500/5 px-4 py-3 text-left text-sm text-cyan-100 transition hover:border-cyan-400/50 hover:bg-cyan-500/10 disabled:opacity-50"
          >
            <span className="text-xl">{emoji}</span>
            <span>{label}</span>
            {sending ? (
              <span className="ml-auto text-[10px] text-cyan-400">Abriendo…</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export default function SupportChatPanel({ onClose, onMessageRead }: Props) {
  const [mounted, setMounted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [conversation, setConversation] = useState<SupportConversation | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [showNewReport, setShowNewReport] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const loadConversation = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchUserSupportConversations();
      const open = list.find((c) => c.status !== "resolved") ?? null;
      setShowNewReport(false);
      setConversation(open);
      if (open) {
        const msgs = await fetchSupportMessages(open.id);
        setMessages(msgs);
        await markSupportConversationRead(open.id);
        onMessageRead();
      } else {
        setMessages([]);
      }
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "No se pudo cargar el soporte. Inicia sesión e intenta de nuevo.",
      );
    } finally {
      setLoading(false);
    }
  }, [onMessageRead]);

  useEffect(() => {
    void loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    if (!conversation?.id) return;
    const pollMessages = async () => {
      try {
        const [msgs, list] = await Promise.all([
          fetchSupportMessages(conversation.id),
          fetchUserSupportConversations(),
        ]);
        setMessages(msgs);
        const fresh = list.find((c) => c.id === conversation.id);
        if (fresh?.unread_by_user) {
          await markSupportConversationRead(conversation.id);
          onMessageRead();
        }
      } catch {
        /* ignore */
      }
    };
    const interval = window.setInterval(() => void pollMessages(), 8_000);
    return () => window.clearInterval(interval);
  }, [conversation?.id, onMessageRead]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const startCategory = async (category: SupportCategory) => {
    setSending(true);
    setError(null);
    try {
      const conv = await createSupportConversation(category);
      setConversation(conv);
      setMessages([]);
      setShowNewReport(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al crear conversación");
    } finally {
      setSending(false);
    }
  };

  const beginNewReport = () => {
    setShowNewReport(true);
    setText("");
    setPendingFiles([]);
    setError(null);
  };

  const showCategoryPicker = !conversation || showNewReport;

  const handleSend = async () => {
    if (!conversation || sending) return;
    const content = text.trim();
    if (!content && pendingFiles.length === 0) return;
    setSending(true);
    setError(null);
    try {
      const attachmentUrls: string[] = [];
      for (const file of pendingFiles) {
        const url = await uploadSupportAttachment(conversation.id, file);
        if (url) attachmentUrls.push(url);
      }
      const msg = await sendSupportMessage(conversation.id, content, attachmentUrls);
      if (msg) setMessages((prev) => [...prev, msg]);
      setText("");
      setPendingFiles([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar");
    } finally {
      setSending(false);
    }
  };

  const onFilePick = (files: FileList | null) => {
    if (!files?.length) return;
    const next = Array.from(files).filter((f) => f.type.startsWith("image/"));
    setPendingFiles((prev) => [...prev, ...next].slice(0, 3));
  };

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[130] flex flex-col overflow-hidden border-cyan-500/30 bg-[#0a0f18] shadow-2xl sm:inset-auto sm:bottom-24 sm:right-6 sm:h-[min(560px,calc(100vh-7rem))] sm:w-[min(380px,calc(100vw-1.5rem))] sm:rounded-2xl sm:border">
      <header className="flex shrink-0 items-center justify-between border-b border-cyan-500/20 bg-gradient-to-r from-purple-900/40 to-blue-900/40 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded px-1 py-1 font-[family-name:var(--font-orbitron)] text-[10px] font-semibold tracking-wide text-cyan-400 hover:bg-cyan-500/10 sm:hidden"
            aria-label="Volver"
          >
            ← VOLVER
          </button>
          <div className="min-w-0">
            <p className="font-[family-name:var(--font-orbitron)] text-sm font-bold text-cyan-200">
              Soporte CED
            </p>
            <p className="text-[11px] text-cyan-500/80">Escríbenos directamente</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded p-1 text-cyan-400 hover:bg-cyan-500/10"
          aria-label="Cerrar"
        >
          <X size={18} />
        </button>
      </header>

      {conversation && !showNewReport ? (
        <div className="shrink-0 border-b border-cyan-500/15 px-4 py-2">
          <button
            type="button"
            onClick={beginNewReport}
            className="w-full rounded-lg border border-cyan-500/30 bg-cyan-500/5 py-2 text-center text-[11px] font-semibold tracking-wide text-cyan-300 transition hover:border-cyan-400/50 hover:bg-cyan-500/10"
          >
            + Nuevo reporte
          </button>
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto p-4">
        {error ? (
          <div className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        ) : null}

        {loading ? (
          <p className="text-sm text-cyan-500/70">Cargando…</p>
        ) : showCategoryPicker ? (
          <div className="space-y-3">
            {conversation && showNewReport ? (
              <button
                type="button"
                onClick={() => setShowNewReport(false)}
                className="text-[11px] font-medium text-cyan-400 underline-offset-2 hover:underline"
              >
                ← Volver al reporte actual
              </button>
            ) : null}
            <CategoryPicker
              sending={sending}
              onPick={(key) => void startCategory(key)}
            />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-lg border border-cyan-500/15 bg-cyan-500/5 px-3 py-2 text-[11px] text-cyan-400">
              {SUPPORT_CATEGORY_LABELS[conversation.category].emoji}{" "}
              {SUPPORT_CATEGORY_LABELS[conversation.category].label}
              {conversation.status === "resolved" ? " · Resuelto" : ""}
            </div>
            {messages.length === 0 ? (
              <p className="text-xs text-cyan-500/70">
                Cuéntanos tu caso abajo. Te responderemos pronto.
              </p>
            ) : null}
            {messages.map((m) => {
              const isUser = m.sender_type === "user";
              return (
                <div
                  key={m.id}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                      isUser
                        ? "rounded-br-md bg-gradient-to-br from-purple-600 to-blue-600 text-white"
                        : "rounded-bl-md border border-cyan-500/20 bg-[#111827] text-cyan-50"
                    }`}
                  >
                    {m.content ? <p className="whitespace-pre-wrap break-words">{m.content}</p> : null}
                    {m.attachments?.map((url) => (
                      <a
                        key={url}
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 block"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={url}
                          alt="Adjunto"
                          className="max-h-40 rounded-lg border border-white/10 object-cover"
                        />
                      </a>
                    ))}
                    <p className={`mt-1 text-[10px] ${isUser ? "text-white/70" : "text-cyan-500/60"}`}>
                      {formatTime(m.created_at)}
                    </p>
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {conversation && !showNewReport ? (
        <footer className="shrink-0 border-t border-cyan-500/20 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          {pendingFiles.length > 0 ? (
            <div className="mb-2 flex flex-wrap gap-2">
              {pendingFiles.map((f) => (
                <span
                  key={f.name + f.size}
                  className="rounded bg-cyan-500/10 px-2 py-1 text-[10px] text-cyan-300"
                >
                  {f.name}
                </span>
              ))}
            </div>
          ) : null}
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => onFilePick(e.target.files)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg border border-cyan-500/30 p-2 text-cyan-400 hover:bg-cyan-500/10"
              aria-label="Adjuntar imagen"
            >
              <ImagePlus size={18} />
            </button>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              placeholder="Escribe tu mensaje…"
              className="min-h-[44px] flex-1 resize-none rounded-lg border border-cyan-500/25 bg-black/40 px-3 py-2 text-sm text-cyan-50 outline-none focus:border-cyan-400/50"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
            />
            <button
              type="button"
              disabled={sending}
              onClick={() => void handleSend()}
              className="rounded-lg bg-gradient-to-br from-purple-600 to-blue-600 p-2 text-white disabled:opacity-50"
              aria-label="Enviar"
            >
              <Send size={18} />
            </button>
          </div>
        </footer>
      ) : (
        <footer className="shrink-0 border-t border-cyan-500/20 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-center text-[11px] text-cyan-500/70">
          Elige una categoría arriba para abrir el chat.
        </footer>
      )}
    </div>,
    document.body,
  );
}
