"use client";

import { Send, Wallet, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { appendStreamChunk } from "@/lib/stream-chunk";
import { coerceDisplayText } from "@/lib/display-text";
import type { ChatPdfAttachment } from "@/lib/api/chat";
import {
  FINANCE_DEFAULT_WELCOME,
  fetchFinanceChatStatus,
  sendFinanceChatMessage,
  sendFinanceChatMessageStream,
  type FinanceChatMessage,
} from "@/lib/api/finance";
import { fetchFitlineActionPlan } from "@/lib/api/opportunitiesPilot";
import { downloadPdfBlob } from "@/lib/api/pdf";
import { FinanceLedgerPanel } from "@/components/chat/FinanceLedgerPanel";

type FinanceChatPanelProps = {
  open: boolean;
  onClose: () => void;
  variant?: "overlay" | "embedded";
};

function stripPdfLinks(content: unknown): string {
  return coerceDisplayText(content)
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
        className="inline-flex items-center gap-1.5 rounded border border-[var(--ced-cyan)]/50 bg-[var(--ced-cyan)]/10 px-3 py-2 text-[11px] font-semibold text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/20 disabled:opacity-60"
      >
        {busy ? "Descargando…" : `📄 Descargar PDF${pdf.title ? `: ${pdf.title}` : ""}`}
      </button>
      {error ? <p className="mt-1 text-[10px] text-red-400">{error}</p> : null}
    </div>
  );
}

export function FinanceChatPanel({
  open,
  onClose,
  variant = "overlay",
}: FinanceChatPanelProps) {
  const [messages, setMessages] = useState<FinanceChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [actionPlan, setActionPlan] = useState<{
    title?: string;
    content?: { goals?: string[]; steps?: string[]; notes?: string };
  } | null>(null);
  const [tab, setTab] = useState<"chat" | "movimientos" | "papelera">("chat");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef(messages);
  const streamTargetIndexRef = useRef<number | null>(null);
  const submitInFlightRef = useRef(false);

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
    void fetchFitlineActionPlan()
      .then((res) => {
        if (cancelled) return;
        const plan = res?.plan;
        if (plan && typeof plan === "object") {
          setActionPlan(plan as {
            title?: string;
            content?: { goals?: string[]; steps?: string[]; notes?: string };
          });
        } else {
          setActionPlan(null);
        }
      })
      .catch(() => {
        if (!cancelled) setActionPlan(null);
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
    if (!text || configured === false) return;
    if (submitInFlightRef.current) return;
    submitInFlightRef.current = true;
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
      const idx = assistantIndex;
      setMessages((prev) => {
        if (idx < 0 || idx >= prev.length) return prev;
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
      const idx = assistantIndex;
      setMessages((prev) => {
        if (idx < 0 || idx >= prev.length) return prev;
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
        const idx = assistantIndex;
        setMessages((prev) => {
          if (idx >= 0 && idx < prev.length) {
            const target = prev[idx];
            if (target?.role === "assistant" && target.content.trim()) {
              return prev;
            }
          }
          return prev.filter((m, i) => i !== idx || m.content.trim() !== "");
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
      submitInFlightRef.current = false;
      textareaRef.current?.focus();
    }
  }, [configured, input]);

  if (!open) return null;

  const embedded = variant === "embedded";
  const panel = (
      <div
        className={
          embedded
            ? "flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--studio-chat-bg)] text-[var(--studio-chat-fg)]"
            : "box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-[var(--studio-border)] bg-[var(--studio-chat-bg)] text-[var(--studio-chat-fg)] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-lg sm:rounded-2xl"
        }
      >
        {embedded ? null : (
        <header className="flex shrink-0 items-center justify-between border-b border-[var(--studio-border)] px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Wallet className="h-4 w-4 shrink-0 text-[var(--ced-cyan)]" />
            <div className="min-w-0">
              <p className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-[var(--ced-cyan)]">
                FINANZAS
              </p>
              <p className="truncate text-[10px] text-[var(--ced-text-muted)]">
                Gastos, ingresos y ahorro
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10"
            aria-label="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </header>
        )}

        <div className="flex shrink-0 gap-1 border-b border-[var(--studio-border)] px-3 py-1.5">
          {(
            [
              ["chat", "Chat"],
              ["movimientos", "Movimientos"],
              ["papelera", "Papelera"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded px-2 py-1 text-[10px] font-semibold uppercase tracking-wider ${
                tab === id
                  ? "bg-[var(--ced-cyan)]/20 text-[var(--ced-text-primary)]"
                  : "text-[var(--ced-text-muted)] hover:text-[var(--ced-cyan)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab !== "chat" ? <FinanceLedgerPanel tab={tab} /> : null}

        {tab === "chat" && configured === false ? (
          <p className="mx-4 mt-3 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
            Finanzas no disponible en este momento. Intente de nuevo más tarde.
          </p>
        ) : null}

        {tab === "chat" && actionPlan ? (
          <div className="mx-4 mt-3 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-card)] px-3 py-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--ced-cyan)]">
              Plan de acción guardado
            </p>
            <p className="mt-0.5 text-xs text-[var(--studio-chat-fg)]">
              {actionPlan.title || "Plan de crecimiento"}
            </p>
            {Array.isArray(actionPlan.content?.goals) &&
            actionPlan.content.goals.length > 0 ? (
              <ul className="mt-1 list-inside list-disc text-[11px] text-[var(--ced-text-muted)]">
                {actionPlan.content.goals.slice(0, 4).map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {tab === "chat" ? (
        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3"
        >
          {messages.map((msg, i) => {
            const displayContent =
              msg.role === "assistant"
                ? stripPdfLinks(msg.content)
                : coerceDisplayText(msg.content);
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
                  "max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "ml-auto ced-studio-user-bubble"
                    : "mr-auto ced-studio-ced-bubble",
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
            <p className="animate-pulse text-[11px] text-[var(--studio-hint)]">
              {statusHint || "CED está escribiendo…"}
            </p>
          ) : busy ? (
            <p className="text-[11px] text-[var(--studio-hint)]">Procesando…</p>
          ) : null}
        </div>
        ) : null}

        {tab === "chat" && error ? (
          <p className="mx-4 mb-2 text-[11px] text-red-400">{error}</p>
        ) : null}

        {tab === "chat" ? (
        <footer className={`relative z-10 shrink-0 border-t border-[var(--studio-border)] bg-[var(--studio-chat-bg)] px-3 pt-2 pb-2 sm:px-4 sm:pt-3 ${embedded ? "lg:pb-3" : "pb-[max(0.75rem,env(safe-area-inset-bottom))]"}`}>
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
              className="min-h-[56px] max-h-40 flex-1 resize-y rounded-xl border border-[var(--studio-border)] bg-[var(--studio-composer-bg)] px-3 py-2 text-base text-[var(--studio-composer-fg)] placeholder:text-[var(--studio-hint)] focus:border-[var(--ced-cyan)] focus:outline-none disabled:opacity-50 sm:text-[12px]"
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || !input.trim() || configured === false}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--ced-cyan)]/50 bg-[var(--ced-cyan)]/15 text-[var(--ced-cyan)] transition hover:bg-[var(--ced-cyan)]/25 disabled:opacity-40"
              aria-label="Enviar"
              title="ENVIAR"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-center text-[9px] text-[var(--studio-hint)]">
            Registro · Análisis · Plan de ahorro · Enter
          </p>
        </footer>
        ) : null}
      </div>
  );

  if (embedded) return panel;

  return (
    <div className="fixed inset-0 z-[155] flex items-end justify-center overflow-x-hidden bg-black/55 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      {panel}
    </div>
  );
}
