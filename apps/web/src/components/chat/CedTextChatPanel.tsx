"use client";

import { MessageCircle, Minimize2, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchChatStatus,
  sendChatMessage,
  type ChatMessage,
  type ChatStatus,
} from "@/lib/api/chat";

type CedTextChatPanelProps = {
  open: boolean;
  onClose: () => void;
};

function formatTime(iso?: string) {
  if (!iso) {
    return new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  }
  return new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

export function CedTextChatPanel({ open, onClose }: CedTextChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshStatus = useCallback(async () => {
    const s = await fetchChatStatus();
    setStatus(s);
  }, []);

  useEffect(() => {
    if (!open) return;
    void refreshStatus();
    if (messages.length === 0) {
      setMessages([
        {
          role: "model",
          content:
            "Hola, soy CED. Puedes escribirme aquí o usar el micrófono cuando quieras voz en vivo.",
        },
      ]);
    }
  }, [open, messages.length, refreshStatus]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const submit = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setInput("");
    setBusy(true);
    setTyping(true);
    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const result = await sendChatMessage(text, conversationId);
      setConversationId(result.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "model", content: result.reply, created_at: new Date().toISOString() },
      ]);
      setStatus(result.usage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar.");
    } finally {
      setBusy(false);
      setTyping(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex justify-end bg-black/40 backdrop-blur-[1px]">
      <div className="flex h-full w-full max-w-md flex-col border-l border-cyan-500/30 bg-[#060a0f] shadow-2xl">
        <header className="flex items-center justify-between border-b border-cyan-500/20 px-4 py-3">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-cyan-400" />
            <span className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-300">
              CHAT con CED
            </span>
          </div>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1.5 text-cyan-600 hover:bg-cyan-500/10 hover:text-cyan-300"
              aria-label="Minimizar"
            >
              <Minimize2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1.5 text-cyan-600 hover:bg-cyan-500/10 hover:text-cyan-300"
              aria-label="Cerrar"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        {status && !status.unlimited && status.messages_limit_daily != null && (
          <p className="border-b border-cyan-900/40 px-4 py-1.5 text-[10px] text-cyan-600">
            Mensajes hoy: {status.messages_used_today}/{status.messages_limit_daily}
          </p>
        )}

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.map((msg, i) => {
            const isUser = msg.role === "user";
            return (
              <div
                key={`${msg.role}-${i}`}
                className={`flex ${isUser ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    isUser
                      ? "bg-cyan-500/15 text-cyan-50"
                      : "border border-cyan-500/25 bg-black/60 text-cyan-100/90"
                  }`}
                >
                  {!isUser && (
                    <div className="mb-1 font-[family-name:var(--font-orbitron)] text-[9px] text-cyan-500">
                      CED
                    </div>
                  )}
                  <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                  <p className="mt-1 text-[9px] opacity-50">{formatTime(msg.created_at)}</p>
                </div>
              </div>
            );
          })}
          {typing && (
            <p className="text-xs text-cyan-500 animate-pulse">CED está escribiendo…</p>
          )}
        </div>

        {error && <p className="px-4 pb-1 text-xs text-red-400">{error}</p>}

        <footer className="border-t border-cyan-500/20 p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submit();
                }
              }}
              rows={2}
              placeholder="Escribe a CED…"
              disabled={busy || status?.blocked}
              className="flex-1 resize-none rounded border border-cyan-800/50 bg-black/50 px-3 py-2 text-sm text-white placeholder:text-cyan-800 focus:border-cyan-500 focus:outline-none disabled:opacity-50"
            />
            <button
              type="button"
              disabled={busy || !input.trim() || status?.blocked}
              onClick={() => void submit()}
              className="flex h-auto items-center justify-center rounded border border-cyan-400/60 px-3 text-cyan-300 hover:bg-cyan-400/10 disabled:opacity-40"
              aria-label="Enviar"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-[9px] text-cyan-700">Enter envía · Shift+Enter nueva línea</p>
        </footer>
      </div>
    </div>
  );
}
