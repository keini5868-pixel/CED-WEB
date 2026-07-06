"use client";

import { Brain, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatImageAttachment, ChatPdfAttachment } from "@/lib/api/chat";
import {
  fetchAdvancedChatStatus,
  sendAdvancedChatMessage,
  sendAdvancedChatMessageStream,
  type AdvancedChatMessage,
} from "@/lib/api/advanced";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";
import { downloadGeneratedImage } from "@/lib/api/image-download";
import { downloadPdfBlob } from "@/lib/api/pdf";

type AdvancedChatPanelProps = {
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
      await downloadPdfBlob(pdf.file_id, pdf.filename || "documento-ced.pdf");
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
        className="inline-flex items-center gap-1.5 rounded border border-violet-400/50 bg-violet-400/10 px-3 py-2 text-[11px] font-semibold text-violet-200 hover:bg-violet-400/20 disabled:opacity-60"
      >
        {busy ? "Descargando…" : `📄 Descargar PDF${pdf.title ? `: ${pdf.title}` : ""}`}
      </button>
      {error ? <p className="mt-1 text-[10px] text-red-400">{error}</p> : null}
    </div>
  );
}

function ChatImagePreview({ image }: { image: ChatImageAttachment }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const src = normalizeCedMediaUrl(image.url);
  const label = image.caption?.trim() || image.prompt?.trim() || "Imagen generada";

  const handleDownload = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadGeneratedImage(image.url, label);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo descargar la imagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 space-y-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={label}
        className="max-h-56 w-full rounded border border-violet-800/50 object-contain"
        onError={(e) => {
          e.currentTarget.alt = "No se pudo cargar la imagen";
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => void handleDownload()}
        className="inline-flex items-center gap-1.5 rounded border border-violet-400/40 bg-violet-400/10 px-2 py-1.5 text-[10px] text-violet-200 hover:bg-violet-400/20 disabled:opacity-60"
      >
        {busy ? "Descargando…" : "🖼️ Descargar imagen"}
      </button>
      {error ? <p className="text-[10px] text-red-400">{error}</p> : null}
    </div>
  );
}

export function AdvancedChatPanel({ open, onClose }: AdvancedChatPanelProps) {
  const [messages, setMessages] = useState<AdvancedChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelLabel, setModelLabel] = useState("Claude Haiku");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef(messages);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    void fetchAdvancedChatStatus().then((status) => {
      setConfigured(status?.configured ?? false);
      if (status?.model) {
        setModelLabel(
          (status.stream_model ?? status.model)
            .replace("claude-", "Claude ")
            .replace(/-/g, " "),
        );
      }
      if (messages.length === 0) {
        setMessages([
          {
            role: "assistant",
            content:
              "Modo avanzado activo. Puedo analizar, generar PDFs, crear imágenes y responder prompts largos. ¿Qué desea analizar, señor?",
          },
        ]);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- welcome solo al abrir
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, streaming]);

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
    const historyBefore = messagesRef.current;
    setMessages((prev) => [...prev, userMsg]);

    const assistantPlaceholder: AdvancedChatMessage = {
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, assistantPlaceholder]);
    setStreaming(true);
    setStatusHint("Conectando con Claude…");

    const applyResult = (result: {
      response: string;
      model: string;
      pdf?: ChatPdfAttachment | null;
      image?: ChatImageAttachment | null;
    }) => {
      setModelLabel(result.model.replace("claude-", "Claude ").replace(/-/g, " "));
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (!last || last.role !== "assistant") return prev;
        next[next.length - 1] = {
          ...last,
          content: stripPdfLinks(result.response),
          pdf: result.pdf ?? null,
          image: result.image ?? null,
        };
        return next;
      });
    };

    try {
      const result = await sendAdvancedChatMessageStream(
        text,
        historyBefore,
        (chunk) => {
          setStatusHint(null);
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (!last || last.role !== "assistant") return prev;
            next[next.length - 1] = {
              ...last,
              content: `${last.content}${chunk}`,
            };
            return next;
          });
        },
        (hint) => setStatusHint(hint),
      );
      applyResult(result);
    } catch (streamErr) {
      try {
        setStatusHint("Reintentando sin streaming…");
        const fallback = await sendAdvancedChatMessage(text, historyBefore);
        applyResult(fallback);
      } catch (err) {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.content.trim()) {
            return prev;
          }
          return prev.filter((m) => m.content !== "" || m.role !== "assistant");
        });
        setError(
          err instanceof Error
            ? err.message
            : streamErr instanceof Error
              ? streamErr.message
              : "Error al analizar.",
        );
      }
    } finally {
      setStreaming(false);
      setStatusHint(null);
      setBusy(false);
      textareaRef.current?.focus();
    }
  }, [busy, input]);

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
          {messages.map((msg, i) => {
            const displayContent =
              msg.role === "assistant" ? stripPdfLinks(msg.content) : msg.content;
            if (msg.role === "assistant" && !displayContent && !msg.pdf && !msg.image) {
              return null;
            }
            return (
              <div
                key={`${msg.role}-${i}`}
                className={[
                  "max-w-[92%] rounded-lg px-3 py-2 text-[12px] leading-relaxed",
                  msg.role === "user"
                    ? "ml-auto border border-violet-500/30 bg-violet-950/40 text-violet-50"
                    : "mr-auto border border-violet-900/50 bg-black/50 text-violet-100/95",
                ].join(" ")}
              >
                {displayContent ? (
                  <p className="whitespace-pre-wrap">{displayContent}</p>
                ) : null}
                {msg.pdf?.file_id ? <PdfDownloadButton pdf={msg.pdf} /> : null}
                {msg.image?.url ? <ChatImagePreview image={msg.image} /> : null}
              </div>
            );
          })}
          {streaming ? (
            <p className="ced-hud-text-muted animate-pulse text-[11px]">
              {statusHint || "Claude escribiendo…"}
            </p>
          ) : busy ? (
            <p className="ced-hud-text-muted text-[11px]">Procesando…</p>
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
              rows={3}
              placeholder="Análisis, PDF, imágenes o prompts largos…"
              disabled={busy || configured === false}
              className="min-h-[56px] max-h-40 flex-1 resize-y rounded border border-violet-900/50 bg-black/60 px-3 py-2 text-[12px] text-violet-50 placeholder:text-violet-700 focus:border-violet-500/50 focus:outline-none"
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
          <p className="mt-1 text-center text-[9px] text-violet-500/70">
            PDF · Imágenes · Streaming · Enter
          </p>
        </footer>
      </div>
    </div>
  );
}
