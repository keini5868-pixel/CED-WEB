"use client";

import { MessageCircle, Minimize2, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ImageUploadButton } from "@/components/chat/ImageUploadButton";
import { MicButton } from "@/components/chat/MicButton";
import {
  fetchChatStatus,
  sendChatMessage,
  type ChatImageAttachment,
  type ChatMessage,
  type ChatPdfAttachment,
  type ChatStatus,
} from "@/lib/api/chat";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";
import { downloadGeneratedImage } from "@/lib/api/image-download";
import { downloadPdfBlob } from "@/lib/api/pdf";

type CedTextChatPanelProps = {
  open: boolean;
  onClose: () => void;
  /** Imagen generada por voz — se muestra al abrir el chat */
  seedImage?: ChatImageAttachment | null;
  onSeedConsumed?: () => void;
};

function formatTime(iso?: string) {
  if (!iso) {
    return new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  }
  return new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

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
      setError(
        e instanceof Error
          ? e.message
          : "No se pudo descargar el PDF.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3">
      <button
        type="button"
        disabled={busy}
        onClick={() => void handleDownload()}
        className="inline-flex items-center gap-1.5 rounded border border-cyan-400/50 bg-cyan-400/10 px-3 py-2 text-[11px] font-semibold tracking-wide text-cyan-200 hover:bg-cyan-400/20 disabled:opacity-60"
      >
        {busy ? "Descargando…" : `📄 Descargar PDF${pdf.title ? `: ${pdf.title}` : ""}`}
      </button>
      {error ? <p className="mt-1 text-[10px] text-red-400">{error}</p> : null}
    </div>
  );
}

function ChatImagePreview({ image }: { image: ChatImageAttachment }) {
  const src = normalizeCedMediaUrl(image.url);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadGeneratedImage(image.url, image.prompt);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo descargar la imagen.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-cyan-500/30 bg-black/40">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={image.prompt || "Imagen generada por CED"}
        className="max-h-64 w-full object-contain"
        onError={(e) => {
          e.currentTarget.alt = "No se pudo cargar la imagen";
        }}
      />
      {image.prompt ? (
        <p className="border-t border-cyan-900/40 px-2 py-1.5 text-[10px] text-cyan-600">
          {image.prompt}
        </p>
      ) : null}
      <div className="border-t border-cyan-900/40 px-2 py-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleDownload()}
          className="inline-flex items-center gap-1.5 rounded border border-cyan-400/50 bg-cyan-400/10 px-3 py-2 text-[11px] font-semibold tracking-wide text-cyan-200 hover:bg-cyan-400/20 disabled:opacity-60"
        >
          {busy ? "Descargando…" : "🖼️ Descargar imagen"}
        </button>
        {error ? <p className="mt-1 text-[10px] text-red-400">{error}</p> : null}
      </div>
    </div>
  );
}

export function CedTextChatPanel({
  open,
  onClose,
  seedImage,
  onSeedConsumed,
}: CedTextChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachedImage, setAttachedImage] = useState<{
    file: File;
    preview: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mobilePanelHeight, setMobilePanelHeight] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;

    const vv = window.visualViewport;
    if (!vv) return;

    const syncViewport = () => {
      const keyboardOffset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty(
        "--ced-keyboard-height",
        `${Math.round(keyboardOffset)}px`,
      );
      if (window.matchMedia("(max-width: 640px)").matches) {
        setMobilePanelHeight(Math.round(vv.height));
      } else {
        setMobilePanelHeight(null);
      }
    };

    const resetViewport = () => {
      document.documentElement.style.setProperty("--ced-keyboard-height", "0px");
      setMobilePanelHeight(null);
    };

    syncViewport();
    vv.addEventListener("resize", syncViewport);
    vv.addEventListener("scroll", syncViewport);
    window.addEventListener("orientationchange", syncViewport);

    return () => {
      vv.removeEventListener("resize", syncViewport);
      vv.removeEventListener("scroll", syncViewport);
      window.removeEventListener("orientationchange", syncViewport);
      resetViewport();
    };
  }, [open]);

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
            "Hola, soy CED. Escríbeme aquí, dicta con el micrófono o adjunta una imagen. También puedo generar imágenes y PDFs.",
        },
      ]);
    }
  }, [open, messages.length, refreshStatus]);

  useEffect(() => {
    if (!open || !seedImage?.url) return;
    const seed = seedImage;
    setMessages((prev) => [
      ...prev,
      {
        role: "model",
        content: seed.prompt
          ? `Imagen generada: ${seed.prompt}`
          : "Imagen generada con IA.",
        created_at: new Date().toISOString(),
        image: seed,
      },
    ]);
    onSeedConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- consumir seed una vez por URL
  }, [seedImage?.url, open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const submit = async () => {
    const text = input.trim();
    if ((!text && !attachedImage) || busy) return;
    setError(null);
    const imageFile = attachedImage?.file ?? null;
    const imagePreview = attachedImage?.preview ?? null;
    setInput("");
    setAttachedImage(null);
    setBusy(true);
    setTyping(true);
    const userMsg: ChatMessage = {
      role: "user",
      content: text || "📷 Imagen adjunta",
      user_image_preview: imagePreview,
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const result = await sendChatMessage(text, conversationId, imageFile);
      setConversationId(result.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "model",
          content: result.reply,
          created_at: new Date().toISOString(),
          pdf: result.pdf ?? null,
          image: result.image
            ? { ...result.image, url: normalizeCedMediaUrl(result.image.url) }
            : null,
        },
      ]);
      setStatus(result.usage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar.");
    } finally {
      setBusy(false);
      setTyping(false);
    }
  };

  const handleTranscription = (text: string) => {
    setInput((prev) => {
      if (prev.trim()) return `${prev.trim()} ${text}`;
      return text;
    });
    textareaRef.current?.focus();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center overflow-x-hidden bg-black/50 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      <div
        className="box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-cyan-500/30 bg-[#060a0f] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-md sm:rounded-2xl sm:border"
        style={
          mobilePanelHeight
            ? { height: mobilePanelHeight, maxHeight: mobilePanelHeight }
            : undefined
        }
      >
        <header className="flex shrink-0 items-center justify-between border-b border-cyan-500/20 px-4 py-3">
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

        {status?.trial_expired && (
          <p className="shrink-0 border-b border-amber-900/40 px-4 py-2 text-[10px] text-amber-400">
            Tu prueba terminó.{" "}
            <a href="/pricing" className="underline">
              Elige un plan
            </a>{" "}
            para seguir chateando.
          </p>
        )}

        {status && !status.unlimited && status.messages_limit_daily != null && !status.trial_expired && (
          <p className="shrink-0 border-b border-cyan-900/40 px-4 py-1.5 text-[10px] text-cyan-600">
            Mensajes hoy: {status.messages_used_today}/{status.messages_limit_daily}
          </p>
        )}

        <div
          ref={scrollRef}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-y-contain px-4 py-4 pb-2"
        >
          {messages.map((msg, i) => {
            const isUser = msg.role === "user";
            const pdfAttachment = msg.pdf ?? null;
            const imageAttachment = msg.image ?? null;
            const userImagePreview = msg.user_image_preview ?? null;
            const displayContent = isUser ? msg.content : stripPdfLinks(msg.content);
            return (
              <div
                key={`${msg.role}-${i}`}
                className={`flex ${isUser ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-lg px-3 py-2 text-sm ${
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
                  <p className="whitespace-pre-wrap break-words">{displayContent}</p>
                  {userImagePreview ? (
                    <div className="relative mt-2 inline-block">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={userImagePreview}
                        alt="Imagen adjunta"
                        className="max-h-36 max-w-[200px] rounded-lg object-cover"
                      />
                    </div>
                  ) : null}
                  {imageAttachment ? <ChatImagePreview image={imageAttachment} /> : null}
                  {pdfAttachment ? <PdfDownloadButton pdf={pdfAttachment} /> : null}
                  <p className="mt-1 text-[9px] opacity-50">{formatTime(msg.created_at)}</p>
                </div>
              </div>
            );
          })}
          {typing && (
            <p className="text-xs text-cyan-500 animate-pulse">CED está escribiendo…</p>
          )}
        </div>

        {error && <p className="shrink-0 px-4 pb-1 text-xs text-red-400">{error}</p>}

        <footer className="shrink-0 border-t border-cyan-500/20 bg-[#060a0f] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4">
          {attachedImage ? (
            <div className="relative mb-2 inline-block">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={attachedImage.preview}
                alt="Adjuntada"
                className="max-h-24 max-w-[150px] rounded-lg object-cover sm:max-h-[100px] sm:max-w-[200px]"
              />
              <button
                type="button"
                onClick={() => setAttachedImage(null)}
                className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-black/70 text-white"
                aria-label="Quitar imagen"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : null}
          <div className="flex w-full max-w-full items-end gap-1.5 sm:gap-2">
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
              onFocus={() => {
                window.setTimeout(() => {
                  scrollRef.current?.scrollTo({
                    top: scrollRef.current.scrollHeight,
                    behavior: "smooth",
                  });
                }, 300);
              }}
              onBlur={() => {
                document.documentElement.style.setProperty("--ced-keyboard-height", "0px");
                if (window.matchMedia("(max-width: 640px)").matches && window.visualViewport) {
                  setMobilePanelHeight(Math.round(window.visualViewport.height));
                }
              }}
              rows={1}
              placeholder={
                attachedImage
                  ? "Pregunta algo sobre la imagen…"
                  : "Escribe a CED o usa el micrófono…"
              }
              disabled={busy || status?.blocked}
              className="box-border min-h-[44px] max-h-[120px] min-w-0 flex-1 resize-none overflow-y-auto overflow-x-hidden rounded border border-cyan-800/50 bg-black/50 px-3 py-2.5 text-base leading-snug text-white placeholder:text-cyan-800 focus:border-cyan-500 focus:outline-none disabled:opacity-50 sm:text-sm"
              style={{ WebkitAppearance: "none" }}
            />
            <ImageUploadButton
              onImageSelected={(file, preview) => setAttachedImage({ file, preview })}
              disabled={busy || status?.blocked || !!attachedImage}
            />
            <MicButton
              onTranscription={handleTranscription}
              disabled={busy || status?.blocked}
            />
            <button
              type="button"
              disabled={busy || (!input.trim() && !attachedImage) || status?.blocked}
              onClick={() => void submit()}
              className="box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border border-cyan-400/60 bg-cyan-400/10 text-cyan-300 hover:bg-cyan-400/20 active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px]"
              aria-label="Enviar"
            >
              <Send className="h-[18px] w-[18px] shrink-0" />
            </button>
          </div>
          <p className="mt-1.5 break-words text-left text-[9px] leading-snug text-cyan-700">
            Enter envía · 📷 adjuntar · 🎤 dictar · &quot;genera una imagen de…&quot;
          </p>
        </footer>
      </div>
    </div>
  );
}
