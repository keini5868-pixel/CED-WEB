"use client";

import { Send, Wallet, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { appendStreamChunk } from "@/lib/stream-chunk";
import type { ChatPdfAttachment } from "@/lib/api/chat";
import {
  FINANCE_DEFAULT_WELCOME,
  fetchFinanceChatStatus,
  sendFinanceChatMessage,
  sendFinanceChatMessageStream,
  type FinanceChatMessage,
} from "@/lib/api/finance";
import { downloadPdfBlob } from "@/lib/api/pdf";

type FinanceChatPanelProps = {
  open: boolean;
  onClose: () => void;
};

function stripPdfLinks(content: string): string {
  return content
    .replace(/\[([^\]]*)\]\([^)]*\/pdf\/download\/[a-f0-9]+[^)]*\)/gi, "")
    .replace(/https?:\/\/[^\s)]+(?:\/v1\/pdf|\/api\/ced\/pdf)\/download\/[a-f0-9]+/gi, "")
    .replace(/\/(?:v1\/pdf|api\/ced\/pdf)\/download\/[a-f0-9]+/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function PdfDownloadButton({ pdf }: { pdf: ChatPdfAttachment }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadPdfBlob(pdf.file_id, pdf.filename || "plan-financiero-ced.pdf", {
        allowDuringVoice: true,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo descargar el PDF.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2">
      <button
        type="button"
        disabled={busy}
        onClick={() => void handleDownload()}
        className="inline-flex items-center gap-1.5 rounded border border-emerald-400/50 bg-emerald-400/10 px-3 py-2 text-[11px] font-semibold text-emerald-200 hover:bg-emerald-400/20 disabled:opacity-60"
      >
        {busy ? "Descargando…" : `📄 Descargar PDF${pdf.title ? `: ${pdf.title}` : ""}`}
      </button>
      {error ? <p className="mt-1 text-[10px] text-red-400">{error}</p> : null}
    </div>
  );
}

export function FinanceChatPanel({ open, onClose }: FinanceChatPanelProps) {
  const [messages, setMessages] = useState<FinanceChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef(messages);
  const streamTargetIndexRef = useRef<number | null>(null);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    setMessages((prev) => {
      if (prev.length > 0) return prev;
      return [
        {
          role: "assistant",
          content: FINANCE_DEFAULT_WELCOME,
          created_at: new Date().toISOString(),
        },
      ];
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // Status en background — no bloquea el chat (fail-open, timeout 4s).
    void fetchFinanceChatStatus().then((status) => {
      if (cancelled || !status) return;
      if (status.configured === false) setConfigured(false);
      if (status.finance_db_ready === false && status.finance_db_error) {
        setError(status.finance_db_error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, streaming]);

  const submit = useCallback(async () => {
    const text = input.trim();
    if (!text || busy || configured === false) return;
    setError(null);
    setInput("");
    setBusy(true);

    const sendGuard = setTimeout(() => {
      setBusy(false);
      setStreaming(false);
      setStatusHint(null);
      streamTargetIndexRef.current = null;
    }, 120_000);

    const userMsg: FinanceChatMessage = {
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    const historyBefore = messagesRef.current;
    let assistantIndex = historyBefore.length + 1;
    setMessages((prev) => {
      const next: FinanceChatMessage[] = [
        ...prev,
        userMsg,
        {
          role: "assistant",
          content: "",
          created_at: new Date().toISOString(),
        },
      ];
      assistantIndex = next.length - 1;
      streamTargetIndexRef.current = assistantIndex;
      return next;
    });
    setStreaming(true);
    setStatusHint(null);

    const applyResult = (result: {
      response: string;
      model: string;
      pdf?: ChatPdfAttachment | null;
    }) => {
      setMessages((prev) => {
        const idx = streamTargetIndexRef.current;
        if (idx == null || idx < 0 || idx >= prev.length) return prev;
        const next = [...prev];
        const target = next[idx];
        if (!target || target.role !== "assistant") return prev;
        next[idx] = {
          ...target,
          content: stripPdfLinks(result.response),
          pdf: result.pdf ?? null,
        };
        return next;
      });
    };

    const onChunk = (chunk: string) => {
      setStatusHint(null);
      setMessages((prev) => {
        const idx = streamTargetIndexRef.current;
        if (idx == null || idx < 0 || idx >= prev.length) return prev;
        const next = [...prev];
        const target = next[idx];
        if (!target || target.role !== "assistant") return prev;
        next[idx] = { ...target, content: appendStreamChunk(target.content, chunk) };
        return next;
      });
    };

    try {
      const result = await sendFinanceChatMessageStream(
        text,
        historyBefore,
        onChunk,
        (hint) => setStatusHint(hint),
      );
      applyResult(result);
    } catch (streamErr) {
      try {
        setStatusHint("Reintentando sin streaming…");
        const fallback = await sendFinanceChatMessage(text, historyBefore);
        applyResult(fallback);
      } catch (err) {
        setMessages((prev) => {
          const idx = streamTargetIndexRef.current;
          if (idx != null && idx >= 0 && idx < prev.length) {
            const target = prev[idx];
            if (target?.role === "assistant" && target.content.trim()) {
              return prev;
            }
          }
          return prev.filter(
            (m, i) => i !== streamTargetIndexRef.current || m.content.trim() !== "",
          );
        });
        setError(
          err instanceof Error
            ? err.message
            : streamErr instanceof Error
              ? streamErr.message
              : "Error al procesar sus finanzas.",
        );
      }
    } finally {
      clearTimeout(sendGuard);
      streamTargetIndexRef.current = null;
      setStreaming(false);
      setStatusHint(null);
      setBusy(false);
      textareaRef.current?.focus();
    }
  }, [busy, configured, input]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[155] flex items-end justify-center overflow-x-hidden bg-black/55 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      <div className="box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-emerald-500/35 bg-[#05100b] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-lg sm:rounded-2xl">
        <header className="flex shrink-0 items-center justify-between border-b border-emerald-500/25 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Wallet className="h-4 w-4 shrink-0 text-emerald-300" />
            <div className="min-w-0">
              <p className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-emerald-200">
                💰 FINANZAS
              </p>
              <p className="truncate text-[10px] text-emerald-400/80">
                Gastos, ingresos y ahorro
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-emerald-300 hover:bg-emerald-500/10"
            aria-label="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        {configured === false ? (
          <p className="mx-4 mt-3 rounded border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-200">
            Finanzas no disponible. Configura GOOGLE_API_KEY o ANTHROPIC_API_KEY
            en el servicio API de Railway.
          </p>
        ) : null}

        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3"
        >
          {messages.map((msg, i) => {
            const displayContent =
              msg.role === "assistant" ? stripPdfLinks(msg.content) : msg.content;
            const isActiveStreamBubble =
              streaming && streamTargetIndexRef.current === i;
            if (
              msg.role === "assistant" &&
              !displayContent &&
              !msg.pdf &&
              !isActiveStreamBubble
            ) {
              return null;
            }
            return (
              <div
                key={`${msg.role}-${i}`}
                className={[
                  "max-w-[92%] rounded-lg px-3 py-2 text-[12px] leading-relaxed",
                  msg.role === "user"
                    ? "ml-auto border border-emerald-500/30 bg-emerald-950/40 text-emerald-50"
                    : "mr-auto border border-emerald-900/50 bg-black/50 text-emerald-100/95",
                ].join(" ")}
              >
                {displayContent ? (
                  <p className="whitespace-pre-wrap">{displayContent}</p>
                ) : null}
                {msg.pdf?.file_id ? <PdfDownloadButton pdf={msg.pdf} /> : null}
              </div>
            );
          })}
          {streaming ? (
            <p className="ced-hud-text-muted animate-pulse text-[11px]">
              {statusHint || "CED está escribiendo…"}
            </p>
          ) : busy ? (
            <p className="ced-hud-text-muted text-[11px]">Procesando…</p>
          ) : null}
        </div>

        {error ? (
          <p className="mx-4 mb-2 text-[11px] text-red-400">{error}</p>
        ) : null}

        <footer className="relative z-10 shrink-0 border-t border-emerald-500/20 bg-[#05100b] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4">
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
              rows={3}
              placeholder="Gasté 50 en materiales… / ¿Cómo voy este mes?"
              disabled={configured === false}
              className="min-h-[56px] max-h-40 flex-1 resize-y rounded border border-emerald-900/50 bg-black/60 px-3 py-2 text-base text-emerald-50 placeholder:text-emerald-700 focus:border-emerald-500/50 focus:outline-none disabled:opacity-50 sm:text-[12px]"
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || !input.trim() || configured === false}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded border border-emerald-500/40 bg-emerald-950/50 text-emerald-200 transition hover:bg-emerald-900/50 disabled:opacity-40"
              aria-label="Enviar"
              title="ENVIAR"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-center text-[9px] text-emerald-500/70">
            Registro · Análisis · Plan de ahorro · Enter
          </p>
        </footer>
      </div>
    </div>
  );
}
