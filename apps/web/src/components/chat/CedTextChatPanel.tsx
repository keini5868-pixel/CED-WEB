"use client";

import { MessageCircle, Minimize2, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ImageUploadButton } from "@/components/chat/ImageUploadButton";
import {
  ImageActionBar,
  imageActionHint,
  imageActionPlaceholder,
  type ImageActionMode,
} from "@/components/chat/ImageActionBar";
import { MicButton } from "@/components/chat/MicButton";
import { fetchGenerateImageWithReference } from "@/lib/api/openai";
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
import { useCedOverlay } from "@/contexts/CedOverlayContext";

type CedTextChatPanelProps = {
  open: boolean;
  onClose: () => void;
  /** Imagen generada por voz — se muestra al abrir el chat */
  seedImage?: ChatImageAttachment | null;
  onSeedConsumed?: () => void;
  /** Mientras hay sesión de voz activa, registra imagen para publicar en Instagram */
  onVoiceImageAttached?: (preview: string, file?: File) => void;
  voicePublishActive?: boolean;
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

function dedupeChatMessages(messages: ChatMessage[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  const seenIds = new Set<string>();
  for (const msg of messages) {
    if (msg.id) {
      if (seenIds.has(msg.id)) continue;
      seenIds.add(msg.id);
    }
    const prev = out[out.length - 1];
    if (
      prev &&
      prev.role === msg.role &&
      prev.content.trim() === msg.content.trim() &&
      !msg.pdf &&
      !msg.image &&
      !prev.pdf &&
      !prev.image
    ) {
      continue;
    }
    out.push(msg);
  }
  return out;
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

function ImageLightbox({
  src,
  alt,
  open,
  onClose,
}: {
  src: string;
  alt: string;
  open: boolean;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/92 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Vista ampliada"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-black/70 text-white hover:bg-black"
        aria-label="Cerrar"
      >
        <X className="h-5 w-5" />
      </button>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className="max-h-[92vh] max-w-[96vw] cursor-zoom-out rounded-lg object-contain shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

function isInternalImagePrompt(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (t.startsWith("[[CREATIVO]]")) return true;
  if (/^GENERA\s+(?:UNA?\s+)?IMAGEN/i.test(t)) return true;
  if (t.length >= 80 && /caracter[ií]sticas|beneficios|ventajas|referencia|fondo|vbeneficios/i.test(t)) {
    return true;
  }
  if (t.length >= 40 && /^(Genera un creativo|Genera una imagen de alta calidad|Genera un flyer|Mockup fotorrealista|Usa la imagen adjunta|Creativo cuadrado)/i.test(t)) {
    return true;
  }
  return false;
}

/** Creativos con mucho texto deben pasar por chat (brief limpio + publicar después). */
function shouldRouteAttachmentViaChat(text: string, mode: ImageActionMode): boolean {
  if (mode === "analyze") return true;
  const t = text.trim();
  if (!t) return false;
  if (t.length > 100) return true;
  return /beneficios?|veneficios?|caracter[ií]sticas|puntos clave|ventajas|flyer|creativo|referencia|fondo|genera\s+una\s+imagen|vbeneficios|imegen/i.test(
    t,
  );
}

function imageUserLabel(image: ChatImageAttachment): string {
  const caption = image.caption?.trim();
  if (caption) return caption;
  const prompt = image.prompt?.trim();
  if (prompt && !isInternalImagePrompt(prompt)) return prompt;
  return "Imagen generada por CED";
}

function ChatImagePreview({ image }: { image: ChatImageAttachment }) {
  const src = normalizeCedMediaUrl(image.url);
  const label = imageUserLabel(image);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const handleDownload = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadGeneratedImage(image.url, label);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo descargar la imagen.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="mt-3 overflow-hidden rounded-lg border border-cyan-500/30 bg-black/40">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={label}
          className="max-h-64 w-full cursor-zoom-in object-contain transition hover:opacity-95"
          onClick={() => setLightboxOpen(true)}
          onError={(e) => {
            e.currentTarget.alt = "No se pudo cargar la imagen";
          }}
        />
      {label ? (
        <p className="border-t border-cyan-900/40 px-2 py-1.5 text-[10px] text-cyan-600">
          {label}
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
      <ImageLightbox
        src={src}
        alt={label}
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    </>
  );
}

function UserImagePreview({ preview }: { preview: string }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  return (
    <>
      <div className="relative mt-2 inline-block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={preview}
          alt="Imagen adjunta"
          className="max-h-36 max-w-[200px] cursor-zoom-in rounded-lg object-cover"
          onClick={() => setLightboxOpen(true)}
        />
      </div>
      <ImageLightbox
        src={preview}
        alt="Imagen adjunta"
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    </>
  );
}

export function CedTextChatPanel({
  open,
  onClose,
  seedImage,
  onSeedConsumed,
  onVoiceImageAttached,
  voicePublishActive = false,
}: CedTextChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachedImage, setAttachedImage] = useState<{
    file: File;
    preview: string;
  } | null>(null);
  const [imageMode, setImageMode] = useState<ImageActionMode>("analyze");
  const [isDictating, setIsDictating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const keepInputFocusRef = useRef(false);
  const [mobilePanelHeight, setMobilePanelHeight] = useState<number | null>(null);
  const { setTextChatOpen } = useCedOverlay();

  useEffect(() => {
    setTextChatOpen(open);
    return () => setTextChatOpen(false);
  }, [open, setTextChatOpen]);

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
            "Hola, soy CED. Escríbeme aquí, dicta con el micrófono o adjunta una imagen. Puedo analizarla, generar variaciones o crear imágenes nuevas.",
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
    if (!open) return;
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const focusInput = useCallback(() => {
    const run = () => {
      const el = textareaRef.current;
      if (!el || status?.blocked) return;
      el.focus({ preventScroll: true });
      const len = el.value.length;
      el.selectionStart = len;
      el.selectionEnd = len;
    };
    requestAnimationFrame(() => {
      run();
      requestAnimationFrame(run);
    });
  }, [status?.blocked]);

  useEffect(() => {
    if (!busy) focusInput();
  }, [busy, focusInput]);

  const submit = async () => {
    const text = input.trim();
    if ((!text && !attachedImage) || busy) return;
    keepInputFocusRef.current = true;
    setError(null);
    const imageFile = attachedImage?.file ?? null;
    const imagePreview = attachedImage?.preview ?? null;
    const currentMode = imageMode;
    setInput("");
    setAttachedImage(null);
    setImageMode("analyze");
    setBusy(true);
    setTyping(true);
    focusInput();
    const userMsg: ChatMessage = {
      role: "user",
      content: text || "📷 Imagen adjunta",
      user_image_preview: imagePreview,
    };
    setMessages((prev) => dedupeChatMessages([...prev, userMsg]));

    if (imageFile && imagePreview && onVoiceImageAttached) {
      onVoiceImageAttached(imagePreview, imageFile);
    }

    try {
      if (
        imageFile &&
        !shouldRouteAttachmentViaChat(text, currentMode) &&
        (currentMode === "variation" || currentMode === "inspired" || currentMode === "edit")
      ) {
        const prompt =
          text ||
          (currentMode === "variation"
            ? "Genera una variación de esta imagen"
            : currentMode === "inspired"
              ? "Genera algo con el mismo estilo visual"
              : "Edita esta imagen según lo indicado");
        const result = await fetchGenerateImageWithReference(
          prompt,
          imageFile,
          currentMode,
          "standard",
          imageFile.name || "reference.jpg",
        );
        if (!result.ok) {
          throw new Error(result.error || "No se pudo generar la imagen.");
        }
        const modeLabels: Record<string, string> = {
          variation: "variación",
          inspired: "versión inspirada",
          edit: "imagen editada",
        };
        const imageLabel =
          result.display_label?.trim() ||
          (prompt.length <= 72 && !isInternalImagePrompt(prompt) ? prompt : "Imagen generada por CED");
        setMessages((prev) => [
          ...prev,
          {
            role: "model",
            content: `Aquí está la ${modeLabels[currentMode] || "imagen generada"}:`,
            created_at: new Date().toISOString(),
            image: {
              url: normalizeCedMediaUrl(result.url),
              caption: imageLabel,
              prompt: imageLabel,
              quality: result.quality,
            },
          },
        ]);
        await refreshStatus();
        return;
      }

      const result = await sendChatMessage(
        text,
        conversationId,
        imageFile,
        voicePublishActive || Boolean(onVoiceImageAttached),
      );
      setConversationId(result.conversation_id);
      setMessages((prev) =>
        dedupeChatMessages([
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
        ]),
      );
      setStatus(result.usage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar.");
    } finally {
      setBusy(false);
      setTyping(false);
      keepInputFocusRef.current = false;
      focusInput();
    }
  };

  const handleDictationText = useCallback((text: string) => {
    setInput(text);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      el.selectionStart = el.selectionEnd = text.length;
      el.scrollTop = el.scrollHeight;
    });
  }, []);

  const handleDictatingChange = useCallback((active: boolean) => {
    setIsDictating(active);
    if (!active) {
      textareaRef.current?.focus();
    }
  }, []);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[150] flex items-end justify-center overflow-x-hidden bg-black/50 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      <div
        className="box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-cyan-500/30 bg-[#060a0f] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-md sm:rounded-2xl sm:border"
        style={
          mobilePanelHeight
            ? { height: mobilePanelHeight, maxHeight: mobilePanelHeight }
            : undefined
        }
      >
        <header className="flex shrink-0 items-center justify-between border-b border-cyan-500/20 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 rounded px-1 py-1.5 font-[family-name:var(--font-orbitron)] text-[10px] font-semibold tracking-wide text-cyan-400 hover:bg-cyan-500/10 sm:hidden"
              aria-label="Volver"
            >
              ← VOLVER
            </button>
            <MessageCircle className="h-4 w-4 shrink-0 text-cyan-400" />
            <span className="truncate font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-300">
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
                  {userImagePreview ? <UserImagePreview preview={userImagePreview} /> : null}
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

        <footer className="relative z-10 shrink-0 border-t border-cyan-500/20 bg-[#060a0f] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4">
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
          <div className="flex w-full max-w-full items-end gap-1.5 sm:gap-2">
            <textarea
              ref={textareaRef}
              autoFocus
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
                if (!busy && !keepInputFocusRef.current) return;
                window.setTimeout(() => {
                  if (busy || keepInputFocusRef.current) focusInput();
                }, 10);
              }}
              rows={1}
              enterKeyHint="send"
              inputMode="text"
              aria-label="Escribe tu mensaje a CED"
              placeholder={
                isDictating
                  ? "Escuchando… habla ahora"
                  : attachedImage
                    ? imageActionPlaceholder(imageMode)
                    : busy
                      ? "CED responde… escribe el siguiente mensaje aquí"
                      : "Escribe a CED o usa el micrófono…"
              }
              disabled={Boolean(status?.blocked)}
              className={`box-border min-h-[48px] max-h-[120px] min-w-0 flex-1 resize-none overflow-y-auto overflow-x-hidden rounded-lg border bg-black/60 px-3 py-2.5 text-base leading-snug text-white caret-cyan-300 placeholder:text-cyan-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 disabled:opacity-50 sm:text-sm ${
                isDictating
                  ? "border-red-500/50 focus:border-red-400"
                  : busy
                    ? "border-cyan-500/40"
                    : "border-cyan-700/60 focus:border-cyan-400"
              }`}
              style={{ WebkitAppearance: "none" }}
            />
            <ImageUploadButton
              onImageSelected={(file, preview) => setAttachedImage({ file, preview })}
              disabled={busy || status?.blocked || !!attachedImage}
            />
            <MicButton
              getBaseText={() => input}
              onTextUpdate={handleDictationText}
              onDictatingChange={handleDictatingChange}
              disabled={status?.blocked}
            />
            <button
              type="button"
              disabled={busy || (!input.trim() && !attachedImage) || status?.blocked}
              onPointerDown={(e) => {
                e.preventDefault();
                keepInputFocusRef.current = true;
              }}
              onClick={() => void submit()}
              className="box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border border-cyan-400/60 bg-cyan-400/10 text-cyan-300 hover:bg-cyan-400/20 active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px]"
              aria-label="Enviar"
            >
              <Send className="h-[18px] w-[18px] shrink-0" />
            </button>
          </div>
          <p className="mt-1.5 break-words text-left text-[9px] leading-snug text-cyan-700">
            {isDictating
              ? "🎤 Dictando en vivo… clic en el mic para detener"
              : attachedImage
                ? imageActionHint(imageMode)
                : 'Enter envía · 📷 adjuntar · 🎤 dictar · "genera una imagen de…"'}
          </p>
        </footer>
      </div>
    </div>
  );
}
