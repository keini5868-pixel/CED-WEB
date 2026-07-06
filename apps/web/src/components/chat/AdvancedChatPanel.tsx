"use client";

import { Brain, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchAdvancedChatStatus,
  sendAdvancedChatMessage,
  type AdvancedChatMessage,
} from "@/lib/api/advanced";

type AdvancedChatPanelProps = {
  open: boolean;
  onClose: () => void;
};

export function AdvancedChatPanel({ open, onClose }: AdvancedChatPanelProps) {
  const [messages, setMessages] = useState<AdvancedChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelLabel, setModelLabel] = useState("Claude Opus");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    void fetchAdvancedChatStatus().then((status) => {
      setConfigured(status?.configured ?? false);
      if (status?.model) {
        setModelLabel(status.model.replace("claude-", "Claude ").replace("-", " "));
      }
      if (messages.length === 0) {
        setMessages([
          {
            role: "assistant",
            content:
              "Modo avanzado activo. Puedo ayudarle con análisis de negocio, marketing, ventas y estrategia. ¿Qué desea analizar, señor?",
          },
        ]);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- welcome solo al abrir
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const submit = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setInput("");
    setBusy(true);

    const userMsg: AdvancedChatMessage = {
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const { response, model } = await sendAdvancedChatMessage(text, messages);
      setModelLabel(model.replace("claude-", "Claude ").replace(/-/g, " "));
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al analizar.");
    } finally {
      setBusy(false);
      textareaRef.current?.focus();
    }
  }, [busy, input, messages]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[155] flex items-end justify-center overflow-x-hidden bg-black/55 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      <div className="box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-violet-500/35 bg-[#08060f] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-lg sm:rounded-2xl">
        <header className="flex shrink-0 items-center justify-between border-b border-violet-500/25 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Brain className="h-4 w-4 shrink-0 text-violet-300" />
            <div className="min-w-0">
              <p className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-violet-200">
                ⚡ MODO AVANZADO
              </p>
              <p className="truncate text-[10px] text-violet-400/80">
                Powered by {modelLabel}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-violet-300 hover:bg-violet-500/10"
            aria-label="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        {configured === false ? (
          <p className="mx-4 mt-3 rounded border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-200">
            ANTHROPIC_API_KEY no configurada en Railway. Añádala al servicio API para
            activar el modo avanzado.
          </p>
        ) : null}

        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3"
        >
          {messages.map((msg, i) => (
            <div
              key={`${msg.role}-${i}`}
              className={[
                "max-w-[92%] rounded-lg px-3 py-2 text-[12px] leading-relaxed",
                msg.role === "user"
                  ? "ml-auto border border-violet-500/30 bg-violet-950/40 text-violet-50"
                  : "mr-auto border border-violet-900/50 bg-black/50 text-violet-100/95",
              ].join(" ")}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          ))}
          {busy ? (
            <p className="ced-hud-text-muted text-[11px]">Claude analizando…</p>
          ) : null}
        </div>

        {error ? (
          <p className="mx-4 mb-2 text-[11px] text-red-400">{error}</p>
        ) : null}

        <footer className="shrink-0 border-t border-violet-500/20 p-3">
          <div className="flex gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submit();
                }
              }}
              rows={2}
              placeholder="Escribe tu análisis o pregunta…"
              disabled={busy || configured === false}
              className="min-h-[44px] flex-1 resize-none rounded border border-violet-900/50 bg-black/60 px-3 py-2 text-[12px] text-violet-50 placeholder:text-violet-700 focus:border-violet-500/50 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || !input.trim() || configured === false}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded border border-violet-500/40 bg-violet-950/50 text-violet-200 transition hover:bg-violet-900/50 disabled:opacity-40"
              aria-label="Analizar"
              title="ANALIZAR"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-center text-[9px] text-violet-500/70">ANALIZAR · Enter</p>
        </footer>
      </div>
    </div>
  );
}
