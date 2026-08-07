"use client";

import { Brain, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ImageUploadButton } from "@/components/chat/ImageUploadButton";
import { PdfAttachmentBar } from "@/components/chat/PdfAttachmentBar";
import { PdfUploadButton } from "@/components/chat/PdfUploadButton";
import {
  ImageActionBar,
  imageActionHint,
  imageActionPlaceholder,
  type ImageActionMode,
} from "@/components/chat/ImageActionBar";
import { MicButton } from "@/components/chat/MicButton";
import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { appendStreamChunk } from "@/lib/stream-chunk";
import { coerceDisplayText } from "@/lib/display-text";
import { assertChatMessageLength } from "@/lib/chat-limits";
import type { ChatImageAttachment, ChatPdfAttachment } from "@/lib/api/chat";
import {
  ADVANCED_DEFAULT_WELCOME,
  fetchAdvancedChatStatus,
  sendAdvancedChatMessage,
  sendAdvancedChatMessageStream,
  sendAdvancedChatMessageWithImage,
  sendAdvancedChatMessageWithPdf,
  ADVANCED_TIMEOUT_MS,
  type AdvancedChatMessage,
  type AdvancedImageMode,
} from "@/lib/api/advanced";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";
import { downloadGeneratedImage } from "@/lib/api/image-download";
import { downloadPdfBlob } from "@/lib/api/pdf";

type AdvancedChatPanelProps = {
  open: boolean;
  onClose: () => void;
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
      await downloadPdfBlob(pdf.file_id, pdf.filename || "documento-ced.pdf", {
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
  const [lightboxOpen, setLightboxOpen] = useState(false);
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
        className="max-h-56 w-full cursor-zoom-in rounded border border-violet-800/50 object-contain transition hover:opacity-95"
        onClick={() => setLightboxOpen(true)}
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
      <ImageLightbox
        src={src}
        alt={label}
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    </div>
  );
}

function UserImagePreview({ preview }: { preview: string }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  return (
    <div className="mt-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={preview}
        alt="Imagen adjunta"
        className="max-h-40 cursor-zoom-in rounded border border-violet-800/50 object-contain"
        onClick={() => setLightboxOpen(true)}
      />
      <ImageLightbox
        src={preview}
        alt="Imagen adjunta"
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
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
  const [attachedImage, setAttachedImage] = useState<{
    file: File;
    preview: string;
  } | null>(null);
  const [attachedPdf, setAttachedPdf] = useState<File | null>(null);
  const [imageMode, setImageMode] = useState<ImageActionMode>("analyze");
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
          content: ADVANCED_DEFAULT_WELCOME,
          created_at: new Date().toISOString(),
        },
      ];
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetchAdvancedChatStatus().then((status) => {
      if (cancelled) return;
      // Fail-open: si el fetch de status falla (cold-start/timeout), NO
      // deshabilitamos el chat. Solo bloqueamos si el backend confirma que no
      // está configurado. Así avanzado responde igual que el chat normal.
      if (!status) return;
      setConfigured(status.configured);
      if (status.model) {
        setModelLabel(
          (status.stream_model ?? status.model)
            .replace("claude-", "Claude ")
            .replace(/-/g, " "),
        );
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
    if ((!text && !attachedImage && !attachedPdf) || configured === false) return;
    if (submitInFlightRef.current) return;

    if (!attachedPdf && !attachedImage) {
      const tooLong = assertChatMessageLength(text);
      if (tooLong) {
        setError(tooLong);
        return;
      }
    }

    submitInFlightRef.current = true;
    setError(null);

    const imageFile = attachedImage?.file ?? null;
    const imagePreview = attachedImage?.preview ?? null;
    const pdfFile = attachedPdf;
    const currentMode = imageMode;

    setInput("");
    setAttachedImage(null);
    setAttachedPdf(null);
    setImageMode("analyze");
    setBusy(true);

    const sendGuard = setTimeout(() => {
      setBusy(false);
      setStreaming(false);
      setStatusHint(null);
      streamTargetIndexRef.current = null;
      setError("La operación tardó demasiado. Intente de nuevo.");
    }, ADVANCED_TIMEOUT_MS);

    const userMsg: AdvancedChatMessage = {
      role: "user",
      content: pdfFile
        ? text
          ? `📄 ${pdfFile.name.toLowerCase().endsWith(".docx") ? "Word" : "PDF"}: ${pdfFile.name}\n${text}`
          : `📄 ${pdfFile.name.toLowerCase().endsWith(".docx") ? "Word" : "PDF"}: ${pdfFile.name}`
        : text || "📷 Imagen adjunta",
      created_at: new Date().toISOString(),
      user_image_preview: imagePreview,
    };
    const historyBefore = messagesRef.current;
    let assistantIndex = historyBefore.length + 1;
    setMessages((prev) => {
      const next: AdvancedChatMessage[] = [
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
    const expectsImageGen =
      Boolean(imageFile && (currentMode === "edit" || currentMode === "variation" || currentMode === "inspired")) ||
      (!imageFile &&
        !pdfFile &&
        /\b(genera|crear?|haz(?:me)?|dise[nñ]a)\w*.{0,60}\b(imagen|foto|flyer|creativo|banner)\b/i.test(
          text,
        ));
    setStatusHint(
      pdfFile
        ? "Leyendo documento…"
        : expectsImageGen
          ? "Generando imagen con IA…"
          : null,
    );

    const applyResult = (result: {
      response: string;
      model: string;
      pdf?: ChatPdfAttachment | null;
      image?: ChatImageAttachment | null;
    }) => {
      const idx = assistantIndex;
      setModelLabel(result.model.replace("claude-", "Claude ").replace(/-/g, " "));
      setStatusHint(null);
      const reply = stripPdfLinks(result.response);
      const missingImage =
        expectsImageGen &&
        !result.image?.url &&
        (!reply.trim() ||
          /\b(un\s+momento|estoy\s+generando|voy\s+a\s+generar)\b/i.test(reply) ||
          /listo[^.]*aqu[ií]\s+est/i.test(reply));
      setMessages((prev) => {
        if (idx < 0 || idx >= prev.length) return prev;
        const target = prev[idx];
        if (!target || target.role !== "assistant") return prev;
        const next = [...prev];
        next[idx] = {
          ...target,
          content: missingImage
            ? "No pude generar la imagen a tiempo, señor. Intenta de nuevo en unos segundos."
            : reply,
          pdf: result.pdf ?? null,
          image: result.image?.url
            ? {
                ...result.image,
                url: normalizeCedMediaUrl(result.image.url),
              }
            : null,
        };
        return next;
      });
    };

    let receivedTokens = false;

    const onChunk = (chunk: string) => {
      receivedTokens = true;
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
      if (pdfFile) {
          setStatusHint("Leyendo documento…");
        const result = await sendAdvancedChatMessageWithPdf(
          text,
          historyBefore,
          pdfFile,
        );
        applyResult(result);
      } else if (imageFile) {
        const mode = currentMode as AdvancedImageMode;
        setStatusHint(
          mode === "publish"
            ? "Preparando imagen para publicar…"
            : mode === "analyze"
              ? "Analizando imagen…"
              : "Procesando imagen…",
        );
        const outbound =
          mode === "publish"
            ? text || "Usa esta imagen para publicar"
            : text || "¿Qué piensas de esta imagen?";
        const result = await sendAdvancedChatMessageWithImage(
          outbound,
          historyBefore,
          imageFile,
          mode,
        );
        applyResult(result);
      } else {
        const result = await sendAdvancedChatMessageStream(
          text,
          historyBefore,
          onChunk,
          (hint) => setStatusHint(hint),
        );
        applyResult(result);
      }
    } catch (streamErr) {
      // Con imagen/PDF: no degradar a chat de texto sin adjunto.
      if (!receivedTokens && !imageFile && !pdfFile) {
        try {
          setStatusHint("Reintentando sin streaming…");
          const fallback = await sendAdvancedChatMessage(text, historyBefore);
          applyResult(fallback);
        } catch (err) {
          const idx = assistantIndex;
          setMessages((prev) => {
            if (idx >= 0 && idx < prev.length) {
              const target = prev[idx];
              if (target?.role === "assistant" && (target.content.trim() || target.image?.url)) {
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
                : "Error al enviar.",
          );
        }
      } else {
        const idx = assistantIndex;
        setMessages((prev) => {
          if (idx >= 0 && idx < prev.length) {
            const target = prev[idx];
            if (target?.role === "assistant" && !target.content.trim() && !target.image?.url) {
              return prev.filter((_, i) => i !== idx);
            }
          }
          return prev;
        });
        setError(
          streamErr instanceof Error
            ? streamErr.message
            : imageFile
              ? "No pude procesar la imagen. Intente Analizar de nuevo o «Usar para publicar»."
              : "Error al enviar.",
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
  }, [configured, input, attachedImage, attachedPdf, imageMode]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[155] flex items-end justify-center overflow-x-hidden bg-black/55 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      <div className="box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-violet-500/35 bg-[#08060f] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-lg sm:rounded-2xl">
        <header className="flex shrink-0 items-center justify-between border-b border-violet-500/25 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
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
            Modo avanzado requiere ANTHROPIC_API_KEY en el servicio API de Railway.
          </p>
        ) : null}

        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3"
        >
          {messages.map((msg, i) => {
            const displayContent =
              msg.role === "assistant"
                ? stripPdfLinks(msg.content)
                : coerceDisplayText(msg.content);
            const userImagePreview = msg.user_image_preview ?? null;
            const isActiveStreamBubble =
              streaming && streamTargetIndexRef.current === i;
            if (
              msg.role === "assistant" &&
              !displayContent &&
              !msg.pdf &&
              !msg.image &&
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
                    ? "ml-auto border border-violet-500/30 bg-violet-950/40 text-violet-50"
                    : "mr-auto border border-violet-900/50 bg-black/50 text-violet-100/95",
                ].join(" ")}
              >
                {displayContent ? (
                  <p className="whitespace-pre-wrap">{displayContent}</p>
                ) : isActiveStreamBubble && statusHint ? (
                  <p className="animate-pulse text-violet-300/90">{statusHint}</p>
                ) : null}
                {userImagePreview ? <UserImagePreview preview={userImagePreview} /> : null}
                {msg.pdf?.file_id ? <PdfDownloadButton pdf={msg.pdf} /> : null}
                {msg.image?.url ? <ChatImagePreview image={msg.image} /> : null}
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

        <footer className="relative z-10 shrink-0 border-t border-violet-500/20 bg-[#08060f] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4">
          {attachedPdf ? (
            <PdfAttachmentBar
              filename={attachedPdf.name}
              onRemove={() => setAttachedPdf(null)}
            />
          ) : null}
          {attachedImage ? (
            <ImageActionBar
              preview={attachedImage.preview}
              mode={imageMode}
              onModeChange={setImageMode}
              onRemove={() => {
                setAttachedImage(null);
                setImageMode("analyze");
              }}
            />
          ) : null}
          <div className="flex items-end gap-2">
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
              placeholder={
                attachedPdf
                  ? "Pregunta sobre el PDF o envía para analizarlo…"
                  : attachedImage
                    ? imageActionPlaceholder(imageMode)
                    : "Análisis, PDF, imágenes o dictado por voz…"
              }
              disabled={configured === false}
              className="min-h-[56px] max-h-40 flex-1 resize-y rounded border border-violet-900/50 bg-black/60 px-3 py-2 text-base text-violet-50 placeholder:text-violet-700 focus:border-violet-500/50 focus:outline-none disabled:opacity-50 sm:text-[12px]"
            />
            <PdfUploadButton
              onPdfSelected={(file) => {
                setAttachedPdf(file);
                setAttachedImage(null);
                setImageMode("analyze");
              }}
              disabled={busy || configured === false || !!attachedImage || !!attachedPdf}
            />
            <ImageUploadButton
              onImageSelected={(file, preview) => {
                setAttachedImage({ file, preview });
                setAttachedPdf(null);
              }}
              disabled={busy || configured === false || !!attachedImage || !!attachedPdf}
            />
            <MicButton
              getBaseText={() => input}
              onTextUpdate={setInput}
              disabled={busy || configured === false}
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={
                busy ||
                (!input.trim() && !attachedImage && !attachedPdf) ||
                configured === false
              }
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded border border-violet-500/40 bg-violet-950/50 text-violet-200 transition hover:bg-violet-900/50 disabled:opacity-40"
              aria-label="Analizar"
              title="ANALIZAR"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-center text-[9px] text-violet-500/70">
            {attachedPdf
              ? "PDF listo — envía para que CED lo lea"
              : attachedImage
                ? imageActionHint(imageMode)
                : "📄 PDF · 📷 Imágenes · 🎤 dictado · Enter"}
          </p>
        </footer>
      </div>
    </div>
  );
}
