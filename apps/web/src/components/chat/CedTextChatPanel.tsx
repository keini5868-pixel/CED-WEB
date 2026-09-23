"use client";

import { MessageCircle, Minimize2, Send, X } from "lucide-react";

import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { useCallback, useEffect, useRef, useState } from "react";

import { PdfAttachmentBar } from "@/components/chat/PdfAttachmentBar";
import { AttachMenuButton } from "@/components/chat/AttachMenuButton";
import { SplitPortal, useComposerSplit } from "@/components/chat/ComposerSplit";
import {
  ImageActionBar,
  imageActionHint,
  imageActionPlaceholder,
  type ImageActionMode,
} from "@/components/chat/ImageActionBar";
import { DictationWaveform } from "@/components/chat/DictationWaveform";
import { ChatCopyButton } from "@/components/chat/ChatCopyButton";
import { MicButton } from "@/components/chat/MicButton";
import { fetchGenerateImageWithReference } from "@/lib/api/openai";
import {
  endChatConversation,
  fetchChatStatus,
  sendChatMessage,
  CHAT_DEFAULT_WELCOME,
  type ChatImageAttachment,
  type ChatMessage,
  type ChatPdfAttachment,
  type ChatRechargeNeeded,
  type ChatStatus,
} from "@/lib/api/chat";
import { startRechargeCheckout } from "@/lib/api/billing";
import { appendStreamChunk } from "@/lib/stream-chunk";
import { coerceDisplayText } from "@/lib/display-text";
import { assertChatMessageLength } from "@/lib/chat-limits";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";
import { downloadGeneratedImage } from "@/lib/api/image-download";
import { downloadPdfBlob } from "@/lib/api/pdf";
import { applyCedOpenModule, openFitlineOppsIfRequested } from "@/lib/hud/chrome-events";
import { useCedOverlay } from "@/contexts/CedOverlayContext";
import {
  getConversationMessages,
  peekCachedConversations,
  peekCachedMessages,
  rememberConversationMessages,
  VOICE_THREAD_RESUME_NOTE,
} from "@/lib/api/conversations";

export type LiveVoiceTurn = {
  streamKey: string;
  role: "user" | "model";
  content: string;
  partial?: boolean;
};

type CedTextChatPanelProps = {
  open: boolean;
  onClose: () => void;
  /** Imagen generada por voz — se muestra al abrir el chat */
  seedImage?: ChatImageAttachment | null;
  onSeedConsumed?: () => void;
  /** Prompt desde panel LIFE — se envía al abrir el chat */
  seedPrompt?: string | null;
  onSeedPromptConsumed?: () => void;
  /** Mientras hay sesión de voz activa, registra imagen para publicar en Instagram */
  onVoiceImageAttached?: (preview: string, file?: File) => void;
  voicePublishActive?: boolean;
  /** Chat embebido en el dashboard (sin overlay). */
  variant?: "overlay" | "embedded";
  splitComposer?: boolean;
  /** Cargar un hilo guardado. `""` = chat nuevo. `null` = no hacer nada. */
  resumeConversationId?: string | null;
  /** Incrementa en cada clic para reabrir el mismo hilo. */
  resumeNonce?: number;
  onResumeApplied?: () => void;
  /** Sesión de voz en curso — el transcript se escribe en este chat. */
  voiceSessionActive?: boolean;
  bindVoiceConversationId?: string | null;
  liveVoiceTurns?: LiveVoiceTurn[];
};

function isDefaultWelcome(msg: ChatMessage): boolean {
  return msg.role === "model" && msg.content === CHAT_DEFAULT_WELCOME && !msg.id;
}

const VOICE_LIVE_PREFIX = "voice-live:";

function isVoiceLiveMessage(msg: ChatMessage): boolean {
  return String(msg.id || "").startsWith(VOICE_LIVE_PREFIX);
}

function formatTime(iso?: string) {
  if (!iso) {
    return new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  }
  return new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

function stripPdfLinks(content: unknown): string {
  return coerceDisplayText(content)
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
      !msg.recharge_needed &&
      !prev.pdf &&
      !prev.image &&
      !prev.recharge_needed
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
      await downloadPdfBlob(pdf.file_id, pdf.filename || "documento-ced.pdf", {
        allowDuringVoice: true,
      });
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

const RECHARGE_QUICK_AMOUNTS_CHAT = [10, 25, 50];

function RechargeInChatButton({ recharge }: { recharge: ChatRechargeNeeded }) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRecharge = async (amount: number) => {
    setBusy(amount);
    setError(null);
    try {
      const url = await startRechargeCheckout(amount);
      if (url) window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo iniciar la recarga.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mt-3 rounded border border-amber-500/40 bg-amber-500/10 p-3">
      <p className="text-[11px] font-semibold text-amber-200">
        Límite alcanzado — recarga desde $10
      </p>
      <p className="mt-1 text-[10px] text-amber-100/80">
        {recharge.message ||
          "El crédito es proporcional al monto y no expira. Se aplica a voz, imágenes, búsquedas, PDF y más."}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {RECHARGE_QUICK_AMOUNTS_CHAT.map((amount) => (
          <button
            key={amount}
            type="button"
            disabled={busy !== null}
            onClick={() => void handleRecharge(amount)}
            className="rounded border border-amber-400/60 bg-amber-400/10 px-3 py-1.5 text-[11px] font-bold tracking-wide text-amber-200 hover:bg-amber-400/20 disabled:opacity-60"
          >
            {busy === amount ? "Abriendo…" : `RECARGAR $${amount}`}
          </button>
        ))}
      </div>
      {error ? <p className="mt-1 text-[10px] text-red-400">{error}</p> : null}
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

/** Creativos con mucho texto estructurado deben pasar por chat (brief limpio). */
function shouldRouteAttachmentViaChat(text: string, mode: ImageActionMode): boolean {
  if (mode === "analyze" || mode === "publish") return true;
  const t = text.trim();
  if (!t) return false;
  // En edit/variation/inspired: no forzar creativo de marketing solo por
  // «características» o «hazme una imagen» — eso debe ir al path de referencia.
  if (mode === "edit" || mode === "variation" || mode === "inspired") {
    return /(?:beneficios?|veneficios?|puntos clave|flyer\s+de\s+venta|creativo\s+publicitario)/i.test(
      t,
    );
  }
  if (t.length > 100) return true;
  return /beneficios?|veneficios?|puntos clave|ventajas|flyer|creativo|referencia|fondo|vbeneficios|imegen/i.test(
    t,
  );
}

function looksLikeConversationPaste(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  if (
    t.length > 40 &&
    /(?:tuvimos\s+esta\s+conversaci|horita\s+tuvimos|te\s+pase\s+(?:toda\s+)?(?:esta\s+)?conversaci|conversaci[oó]n.{0,60}recuerdas|recuerdas.{0,80}conversaci)/i.test(
      t,
    )
  ) {
    return true;
  }
  if (t.length < 180) return false;
  const stamps = t.match(/\b\d{1,2}:\d{2}\b/g);
  if ((stamps?.length ?? 0) >= 2) return true;
  if (/^(?:user|ced|assistant)\s*$/gim.test(t) && (t.match(/^(?:user|ced)\s*$/gim)?.length ?? 0) >= 2) {
    return true;
  }
  return false;
}

function looksLikeImageGenerationRequest(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  if (looksLikeConversationPaste(t)) return false;
  return (
    /\b(genera(?:r)?|crear?|haz(?:me)?|dise[nñ]a|ilustra)\w*.{0,80}\b(imagen|foto|flyer|creativo|banner|ilustraci[oó]n)\b/i.test(
      t,
    ) ||
    /\b(necesito|quiero|ayúdame|ayudame).{0,60}\b(genera(?:r)?|crear?|haz)\w*.{0,40}\b(imagen|foto)\b/i.test(
      t,
    ) ||
    /\b(imagen|foto|flyer|creativo)\b.{0,40}\b(con|de|que\s+diga|fondo|tipograf)/i.test(t)
  );
}

function looksLikeImageWaitFiller(text: string): boolean {
  const t = text.trim();
  if (!t || t.length > 280) return false;
  return /\b(un\s+momento|en\s+seguida|estoy\s+generando|voy\s+a\s+generar|generando\s+(?:la\s+)?(?:imagen|foto))\b/i.test(
    t,
  );
}

function recentMessagesAwaitPublish(messages: ChatMessage[]): boolean {
  const recent = messages.slice(-8);
  const blob = recent.map((m) => m.content || "").join(" ");
  // Exige señal clara de flujo de publicación, no mención casual de «redes».
  return /(?:publica(?:r)?\s+(?:en\s+)?(?:facebook|instagram|face|ig|fb)|desea publicar|para publicar)/i.test(
    blob,
  ) && /imagen|foto|adjunt|suba|sube/i.test(blob);
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
  seedPrompt,
  onSeedPromptConsumed,
  onVoiceImageAttached,
  voicePublishActive = false,
  variant = "overlay",
  splitComposer = false,
  resumeConversationId = null,
  resumeNonce = 0,
  onResumeApplied,
  voiceSessionActive = false,
  bindVoiceConversationId = null,
  liveVoiceTurns = [],
}: CedTextChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachedImage, setAttachedImage] = useState<{
    file: File;
    preview: string;
  } | null>(null);
  const [attachedPdf, setAttachedPdf] = useState<File | null>(null);
  const [imageMode, setImageMode] = useState<ImageActionMode>("analyze");
  const [isDictating, setIsDictating] = useState(false);
  const [dictationLevel, setDictationLevel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const resumeLockRef = useRef(false);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const keepInputFocusRef = useRef(false);
  const streamTargetIndexRef = useRef<number | null>(null);
  const [mobilePanelHeight, setMobilePanelHeight] = useState<number | null>(null);
  const { setTextChatOpen } = useCedOverlay();
  const voiceSessionGateRef = useRef(false);
  const embedded = variant === "embedded";
  const { bar: composerBar, actions: composerActions } = useComposerSplit(
    Boolean(open && embedded && splitComposer),
  );

  useEffect(() => {
    if (embedded) return;
    setTextChatOpen(open);
    return () => setTextChatOpen(false);
  }, [embedded, open, setTextChatOpen]);

  useEffect(() => {
    if (!open || embedded) return;

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
  }, [embedded, open]);

  const refreshStatus = useCallback(async () => {
    const s = await fetchChatStatus();
    setStatus(s);
    return s;
  }, []);

  useEffect(() => {
    if (open) return;
    const cid = conversationId;
    const hasUserTurn = messages.some((m) => m.role === "user");
    if (!cid || !hasUserTurn) return;
    void endChatConversation(cid);
  }, [open, conversationId, messages]);

  useEffect(() => {
    if (resumeNonce <= 0) return;
    if (resumeConversationId === null) return;
    let cancelled = false;
    if (resumeConversationId === "") {
      resumeLockRef.current = false;
      setConversationId(null);
      setMessages([
        {
          role: "model",
          content: CHAT_DEFAULT_WELCOME,
          created_at: new Date().toISOString(),
        },
      ]);
      setError(null);
      setInput("");
      onResumeApplied?.();
      return;
    }
    const id = resumeConversationId.trim();
    const applyMapped = (
      raw: { id?: string; role: string; content: string; created_at: string }[],
      channel?: string,
    ) => {
      const mapped: ChatMessage[] = raw.map((m) => ({
        id: m.id,
        role: m.role === "user" ? "user" : "model",
        content: coerceDisplayText(m.content),
        created_at: m.created_at,
      }));
      const fromVoice =
        channel === "voice" ||
        peekCachedConversations()?.some((c) => c.id === id && c.channel === "voice");
      const alreadyNoted = mapped.some((m) =>
        (m.content || "").includes("conversación de voz"),
      );
      const next =
        fromVoice && mapped.length > 0 && !alreadyNoted
          ? [
              {
                role: "model" as const,
                content: VOICE_THREAD_RESUME_NOTE,
                created_at: mapped[0]?.created_at || new Date().toISOString(),
              },
              ...mapped,
            ]
          : mapped;
      setConversationId(id);
      resumeLockRef.current = true;
      setMessages(
        next.length > 0
          ? next
          : [
              {
                role: "model",
                content: CHAT_DEFAULT_WELCOME,
                created_at: new Date().toISOString(),
              },
            ],
      );
      setError(null);
      setInput("");
    };
    const cached = peekCachedMessages(id);
    if (cached && cached.length > 0) {
      applyMapped(cached);
    }
    void (async () => {
      try {
        const data = await getConversationMessages(id);
        if (cancelled) return;
        applyMapped(data.messages || [], data.conversation?.channel);
        rememberConversationMessages(id, data.messages || []);
      } catch {
        if (!cancelled && !(cached && cached.length > 0)) {
          applyMapped([]);
        }
      } finally {
        if (!cancelled) onResumeApplied?.();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resumeNonce, resumeConversationId, onResumeApplied]);

  useEffect(() => {
    if (!bindVoiceConversationId) return;
    setConversationId(bindVoiceConversationId);
  }, [bindVoiceConversationId]);

  useEffect(() => {
    if (voiceSessionActive && !voiceSessionGateRef.current) {
      voiceSessionGateRef.current = true;
      setMessages((prev) =>
        prev.map((m) =>
          isVoiceLiveMessage(m)
            ? {
                ...m,
                id: `voice-kept:${String(m.id).slice(VOICE_LIVE_PREFIX.length)}`,
                partial: false,
              }
            : m,
        ),
      );
    }
    if (!voiceSessionActive) {
      voiceSessionGateRef.current = false;
      setMessages((prev) =>
        prev.map((m) => (m.partial ? { ...m, partial: false } : m)),
      );
    }
  }, [voiceSessionActive]);

  useEffect(() => {
    if (!voiceSessionActive && liveVoiceTurns.length === 0) return;
    const live: ChatMessage[] = liveVoiceTurns
      .filter((item) => Boolean(item.content?.trim()))
      .map((item) => ({
        id: `${VOICE_LIVE_PREFIX}${item.streamKey}`,
        role: item.role === "user" ? "user" : "model",
        content: item.content,
        created_at: new Date().toISOString(),
        partial: Boolean(item.partial),
      }));
    if (live.length === 0) return;
    setMessages((prev) => {
      const rest = prev.filter((m) => !isVoiceLiveMessage(m));
      const usefulRest = rest.filter((m) => !isDefaultWelcome(m));
      return [...usefulRest, ...live];
    });
  }, [liveVoiceTurns, voiceSessionActive]);

  useEffect(() => {
    if (!conversationId) return;
    if (!messages.some((m) => m.role === "user")) return;
    rememberConversationMessages(
      conversationId,
      messages.map((m) => ({
        id: m.id || "",
        role: m.role,
        content: m.content,
        created_at: m.created_at || new Date().toISOString(),
      })),
    );
  }, [conversationId, messages]);

  useEffect(() => {
    if (!open) return;
    setMessages((prev) => {
      if (prev.length > 0) return prev;
      return [
        {
          role: "model",
          content: CHAT_DEFAULT_WELCOME,
          created_at: new Date().toISOString(),
        },
      ];
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void refreshStatus().then((s) => {
      if (cancelled || !s) return;
      setStatus(s);
    });
    void fetchChatStatus({ welcome: true }).then((s) => {
      if (cancelled) return;
      const personalized = s?.welcome_message?.trim();
      if (!personalized) return;
      setMessages((prev) => {
        if (resumeLockRef.current) return prev;
        if (prev.some((m) => m.role === "user" || isVoiceLiveMessage(m))) return prev;
        if (prev.length === 0) {
          return [
            {
              role: "model",
              content: personalized,
              created_at: new Date().toISOString(),
            },
          ];
        }
        if (prev.length === 1 && prev[0]?.role === "model") {
          return [{ ...prev[0], content: personalized }];
        }
        return prev;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [open, refreshStatus]);

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
    if (!open || !seedPrompt?.trim() || busy) return;
    const prompt = seedPrompt.trim();
    onSeedPromptConsumed?.();
    setInput(prompt);
    void (async () => {
      setError(null);
      setBusy(true);
      setTyping(true);
      const userMsg: ChatMessage = { role: "user", content: prompt };
      setMessages((prev) => dedupeChatMessages([...prev, userMsg]));
      setMessages((prev) =>
        dedupeChatMessages([
          ...prev,
          { role: "model", content: "", created_at: new Date().toISOString() },
        ]),
      );
      openFitlineOppsIfRequested(prompt);
      if (looksLikeImageGenerationRequest(prompt)) {
        setStatusHint("Generando imagen con IA…");
        setTyping(true);
      } else {
        setTyping(false);
      }
      try {
        const result = await sendChatMessage(
          prompt,
          conversationId,
          null,
          voicePublishActive || Boolean(onVoiceImageAttached),
          (chunk) => {
            setTyping(false);
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = {
                ...last,
                content: appendStreamChunk(last.content, chunk),
              };
              return dedupeChatMessages(next);
            });
          },
          null,
          (hint) => {
            setStatusHint(hint);
            setTyping(true);
          },
        );
        if (result.conversation_id) setConversationId(result.conversation_id);
        applyCedOpenModule(result.open_module);
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "model") {
            next[next.length - 1] = {
              ...last,
              content: result.reply,
              pdf: result.pdf,
              image: result.image,
              recharge_needed: result.recharge_needed,
            };
          }
          return dedupeChatMessages(next);
        });
        await refreshStatus();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al enviar mensaje.");
      } finally {
        setBusy(false);
        setTyping(false);
        setStatusHint(null);
        setInput("");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- consumir seed una vez
  }, [seedPrompt, open]);

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
    if ((!text && !attachedImage && !attachedPdf) || busy) return;

    if (!attachedPdf && !attachedImage) {
      const tooLong = assertChatMessageLength(text);
      if (tooLong) {
        setError(tooLong);
        return;
      }
    }

    keepInputFocusRef.current = true;
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
    setTyping(true);
    setStatusHint(null);
    focusInput();

    const outboundText =
      currentMode === "publish" && imageFile
        ? text || "Usa esta imagen para publicar"
        : text;

    openFitlineOppsIfRequested(outboundText);

    const expectsImage =
      Boolean(imageFile) ||
      looksLikeImageGenerationRequest(outboundText) ||
      (currentMode === "variation" ||
        currentMode === "inspired" ||
        currentMode === "edit");

    if (pdfFile) {
      setStatusHint("Leyendo documento…");
    } else if (expectsImage) {
      setStatusHint("Generando imagen con IA…");
    }

    const sendGuard = setTimeout(() => {
      setBusy(false);
      setTyping(false);
      setStatusHint(null);
      streamTargetIndexRef.current = null;
      setError(
        pdfFile
          ? "La lectura del PDF tardó demasiado. Intenta de nuevo."
          : expectsImage
            ? "La generación de imagen tardó demasiado. Intenta de nuevo."
            : "La respuesta tardó demasiado. Intenta de nuevo.",
      );
    }, 280_000);

    const userMsg: ChatMessage = {
      role: "user",
      content: pdfFile
        ? outboundText
          ? `📄 ${pdfFile.name.toLowerCase().endsWith(".docx") ? "Word" : "PDF"}: ${pdfFile.name}\n${outboundText}`
          : `📄 ${pdfFile.name.toLowerCase().endsWith(".docx") ? "Word" : "PDF"}: ${pdfFile.name}`
        : outboundText || "📷 Imagen adjunta",
      user_image_preview: imagePreview,
    };

    if (imageFile && imagePreview && onVoiceImageAttached) {
      onVoiceImageAttached(imagePreview, imageFile);
    }

    // Índice local del placeholder: los updaters de React pueden ejecutarse
    // después del finally (que anula el ref), así que el ref no es confiable
    // en el updater final ni en el catch.
    let assistantIndex = -1;

    try {
      if (
        imageFile &&
        !shouldRouteAttachmentViaChat(outboundText, currentMode) &&
        (currentMode === "variation" || currentMode === "inspired" || currentMode === "edit")
      ) {
        setStatusHint("Generando imagen con IA…");
        const prompt =
          outboundText ||
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

      if (!imageFile && !pdfFile) {
        setMessages((prev) => {
          const next = dedupeChatMessages([
            ...prev,
            userMsg,
            { role: "model", content: "", created_at: new Date().toISOString() },
          ]);
          assistantIndex = next.length - 1;
          streamTargetIndexRef.current = assistantIndex;
          return next;
        });
        // Mantener indicador visible hasta status/token/done (no apagar typing aquí).
      } else {
        setMessages((prev) => dedupeChatMessages([...prev, userMsg]));
        streamTargetIndexRef.current = null;
        if (pdfFile) {
          setStatusHint("Leyendo documento…");
        } else if (
          currentMode === "edit" ||
          currentMode === "variation" ||
          currentMode === "inspired" ||
          looksLikeImageGenerationRequest(outboundText)
        ) {
          setStatusHint("Generando imagen con IA…");
        }
      }

      const applyStreamChunk = (chunk: string) => {
        setTyping(false);
        setMessages((prev) => {
          const idx = streamTargetIndexRef.current;
          if (idx == null || idx < 0 || idx >= prev.length) return prev;
          const next = [...prev];
          const target = next[idx];
          if (!target || target.role !== "model") return prev;
          next[idx] = { ...target, content: appendStreamChunk(target.content, chunk) };
          return next;
        });
      };

      const applyStatus = (hint: string) => {
        setStatusHint(hint);
        setTyping(true);
      };

      const result = await sendChatMessage(
        outboundText,
        conversationId,
        imageFile,
        voicePublishActive || Boolean(onVoiceImageAttached),
        !imageFile && !pdfFile ? applyStreamChunk : undefined,
        imageFile ? currentMode : null,
        applyStatus,
        pdfFile,
      );
      setConversationId(result.conversation_id);
      applyCedOpenModule(result.open_module);
      if (imageFile || pdfFile) {
        const reply = result.reply || "";
        const claimsCreativeSuccess =
          /listo[^.]*aqu[ií]\s+est[aá]\s+su\s+creativo/i.test(reply) &&
          !result.image?.url;
        const missingEditImage =
          expectsImage &&
          !result.image?.url &&
          (looksLikeImageWaitFiller(reply) || !reply.trim());
        setMessages((prev) =>
          dedupeChatMessages([
            ...prev,
            {
              role: "model",
              content: claimsCreativeSuccess || missingEditImage
                ? "No pude completar la generación de esa imagen, señor. "
                  + "Puede intentar de nuevo, editarla con otra instrucción, o publicarla si ya la tiene."
                : reply,
              created_at: new Date().toISOString(),
              pdf: result.pdf ?? null,
              image: result.image
                ? { ...result.image, url: normalizeCedMediaUrl(result.image.url) }
                : null,
              recharge_needed: result.recharge_needed ?? null,
            },
          ]),
        );
      } else {
        const reply = result.reply || "";
        const missingImage =
          expectsImage && !result.image?.url && !result.recharge_needed;
        setMessages((prev) => {
          const idx = assistantIndex;
          if (idx < 0 || idx >= prev.length) return prev;
          const next = [...prev];
          const target = next[idx];
          if (target?.role === "model") {
            next[idx] = {
              ...target,
              content: missingImage
                ? reply && !looksLikeImageWaitFiller(reply)
                  ? /no pude|tard[oó] demasiado|no se (?:pudo|adjunt)/i.test(reply)
                    ? reply
                    : `${reply}\n\nNo se adjuntó la imagen. Intenta de nuevo en unos segundos.`
                  : "No pude generar la imagen a tiempo, señor. Intenta de nuevo en unos segundos."
                : reply,
              pdf: result.pdf ?? null,
              image: result.image
                ? { ...result.image, url: normalizeCedMediaUrl(result.image.url) }
                : null,
              recharge_needed: result.recharge_needed ?? null,
            };
          }
          return dedupeChatMessages(next);
        });
      }
      setStatus(result.usage);
    } catch (e) {
      setMessages((prev) => {
        const idx = assistantIndex;
        if (idx >= 0 && idx < prev.length) {
          const target = prev[idx];
          if (target?.role === "model" && !target.content.trim()) {
            return prev.filter((_, i) => i !== idx);
          }
        }
        return prev;
      });
      const raw = e instanceof Error ? e.message : "Error al enviar.";
      setError(
        /respuesta incompleta/i.test(raw)
          ? expectsImage
            ? "No pude generar la imagen. Intenta de nuevo en unos segundos."
            : "No pude completar la respuesta. Intenta de nuevo."
          : raw,
      );
    } finally {
      clearTimeout(sendGuard);
      streamTargetIndexRef.current = null;
      setBusy(false);
      setTyping(false);
      setStatusHint(null);
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

  const shell = (
      <div
        className={
          embedded
            ? "flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--studio-chat-bg)] text-[var(--studio-chat-fg)]"
            : "box-border flex h-[min(92dvh,720px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-cyan-500/30 bg-[#060a0f] shadow-2xl sm:h-[min(85dvh,680px)] sm:max-w-md sm:rounded-2xl sm:border"
        }
        style={
          !embedded && mobilePanelHeight
            ? { height: mobilePanelHeight, maxHeight: mobilePanelHeight }
            : undefined
        }
      >
        {embedded ? null : (
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
        )}

        {status?.trial_expired && (
          <p className={`shrink-0 border-b px-4 py-2 text-[10px] ${embedded ? "border-amber-200 bg-amber-50 text-amber-800" : "border-amber-900/40 text-amber-400"}`}>
            Tu prueba de voz terminó. El chat sigue disponible.{" "}
            <a href="/dashboard/plans" className="underline">
              Ver planes / recargar
            </a>{" "}
            para volver a usar el asistente de voz.
          </p>
        )}

        {status && !status.unlimited && status.messages_limit_daily != null && !status.trial_expired && (
          <p className={`shrink-0 border-b px-4 py-1.5 text-[10px] ${embedded ? "border-[var(--studio-border)] text-[var(--studio-hint)]" : "border-cyan-900/40 text-cyan-600"}`}>
            Mensajes hoy: {status.messages_used_today}/{status.messages_limit_daily}
          </p>
        )}

        <div
          ref={scrollRef}
          className={`min-h-0 flex-1 space-y-3 overflow-x-hidden overflow-y-scroll overscroll-y-contain px-3 py-3 pb-2 sm:px-4 sm:py-4 ${embedded ? "bg-[var(--studio-chat-bg)]" : ""}`}
        >
          {messages.map((msg, i) => {
            const isUser = msg.role === "user";
            const pdfAttachment = msg.pdf ?? null;
            const imageAttachment = msg.image ?? null;
            const rechargeNeeded = msg.recharge_needed ?? null;
            const userImagePreview = msg.user_image_preview ?? null;
            const displayContent = isUser
              ? coerceDisplayText(msg.content)
              : stripPdfLinks(msg.content);
            return (
              <div
                key={`${msg.role}-${i}`}
                className={`flex ${isUser ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm ${
                    embedded
                      ? isUser
                        ? "ced-studio-user-bubble"
                        : "ced-studio-ced-bubble"
                      : isUser
                        ? "bg-cyan-500/15 text-cyan-50"
                        : "border border-cyan-500/25 bg-black/60 text-cyan-100/90"
                  }`}
                >
                  <div className={`mb-1 flex items-center justify-between gap-2 ${embedded ? (isUser ? "text-[var(--studio-label-user)]" : "text-[var(--studio-label-ced)]") : "font-[family-name:var(--font-orbitron)] text-[9px] text-cyan-500"}`}>
                    <span className={`text-[10px] font-bold ${embedded ? "" : "font-[family-name:var(--font-orbitron)] text-[9px] text-cyan-500"}`}>
                      {isUser ? "User" : "CED"}
                    </span>
                    <ChatCopyButton text={displayContent} />
                  </div>
                  {displayContent ? (
                    <p className={`whitespace-pre-wrap break-words ${msg.partial ? "opacity-90" : ""}`}>
                      {displayContent}
                      {msg.partial ? (
                        <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-cyan-400 align-middle" />
                      ) : null}
                    </p>
                  ) : busy && streamTargetIndexRef.current === i ? (
                    <p className={`animate-pulse ${embedded ? "text-[var(--studio-hint)]" : "text-cyan-400/90"}`}>
                      {statusHint || "Generando…"}
                    </p>
                  ) : (
                    <p className="whitespace-pre-wrap break-words">{displayContent}</p>
                  )}

                  {userImagePreview ? <UserImagePreview preview={userImagePreview} /> : null}
                  {imageAttachment ? <ChatImagePreview image={imageAttachment} /> : null}
                  {pdfAttachment ? <PdfDownloadButton pdf={pdfAttachment} /> : null}
                  {rechargeNeeded ? (
                    <RechargeInChatButton recharge={rechargeNeeded} />
                  ) : null}
                  <p className={`mt-1 text-[9px] ${embedded ? "opacity-40" : "opacity-50"}`}>{formatTime(msg.created_at)}</p>
                </div>
              </div>
            );
          })}
          {typing || (busy && statusHint) ? (
            <p className={`animate-pulse text-xs ${embedded ? "text-[var(--studio-hint)]" : "text-cyan-500"}`}>
              {statusHint || "CED está escribiendo…"}
            </p>
          ) : null}
        </div>

        {error && <p className="shrink-0 px-4 pb-1 text-xs text-red-400">{error}</p>}

        <SplitPortal target={composerBar}>
        <footer className={`relative z-20 shrink-0 overflow-visible px-3 ${
          composerBar
            ? "bg-[var(--studio-chat-bg)] pt-1 pb-0"
            : embedded
              ? "border-t border-[var(--studio-border)] bg-[var(--studio-chat-bg)] py-1.5"
              : "border-t border-cyan-500/20 bg-[#060a0f] py-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4"
        }`}>
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
          <div className="flex w-full min-w-0 max-w-full flex-row items-end gap-1.5 sm:gap-2">
            <div className="relative min-w-0 flex-1">
            <textarea
              ref={textareaRef}
              autoFocus={!embedded}
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
              data-ced-hotspot="chat"
              placeholder={
                isDictating
                  ? "Escuchando… habla ahora"
                  : attachedPdf
                    ? "Pregunta sobre el PDF o envía para analizarlo…"
                    : attachedImage
                      ? imageActionPlaceholder(imageMode)
                      : busy
                        ? "CED responde… escribe el siguiente mensaje aquí"
                        : "Escribe a CED o usa el micrófono…"
              }
              disabled={Boolean(status?.blocked)}
              className={`box-border w-full min-w-0 resize-none overflow-y-auto overflow-x-hidden rounded-full px-4 text-base leading-snug focus:outline-none focus:ring-2 disabled:opacity-50 sm:text-sm ${
                composerBar
                  ? "min-h-[42px] max-h-[72px] py-1.5"
                  : "min-h-[48px] max-h-[120px] py-2.5"
              } ${
                embedded
                  ? `border bg-[var(--studio-composer-bg)] text-[var(--studio-composer-fg)] caret-[var(--ced-cyan)] placeholder:text-[var(--studio-hint)] focus:ring-[var(--ced-cyan)]/40 ${
                      isDictating
                        ? "border-red-400"
                        : "border-[var(--studio-border)] focus:border-[var(--ced-cyan)]"
                    }`
                  : `border bg-black/60 text-white caret-cyan-300 placeholder:text-cyan-600 focus:ring-cyan-500/40 ${
                      isDictating
                        ? "border-red-500/50 focus:border-red-400"
                        : busy
                          ? "border-cyan-500/40"
                          : "border-cyan-700/60 focus:border-cyan-400"
                    }`
              }`}
              style={{ WebkitAppearance: "none" }}
            />
            {isDictating ? (
              <div className="pointer-events-none absolute inset-x-3 bottom-1.5">
                <DictationWaveform level={dictationLevel} active />
              </div>
            ) : null}
            </div>
            {composerActions ? null : (
            <div className="flex shrink-0 items-center justify-end gap-1 sm:gap-1.5">
            <AttachMenuButton
              onPdfSelected={(file) => {
                setAttachedPdf(file);
                setAttachedImage(null);
                setImageMode("analyze");
              }}
              onImageSelected={(file, preview) => {
                setAttachedImage({ file, preview });
                setAttachedPdf(null);
                setImageMode((prev) =>
                  prev === "analyze" && recentMessagesAwaitPublish(messages)
                    ? "publish"
                    : prev,
                );
              }}
              disabled={busy || status?.blocked || !!attachedImage || !!attachedPdf}
            />
            <MicButton
              getBaseText={() => input}
              onTextUpdate={handleDictationText}
              onDictatingChange={handleDictatingChange}
              onLevel={setDictationLevel}
              disabled={status?.blocked}
            />
            <button
              type="button"
              disabled={
                busy ||
                (!input.trim() && !attachedImage && !attachedPdf) ||
                status?.blocked
              }
              onPointerDown={(e) => {
                e.preventDefault();
                keepInputFocusRef.current = true;
              }}
              onClick={() => void submit()}
              className={`box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px] ${
                embedded
                  ? "bg-sky-500 text-white shadow-[0_0_12px_rgba(59,183,255,0.45)] hover:bg-sky-400"
                  : "border border-cyan-400/60 bg-cyan-400/10 text-cyan-300 hover:bg-cyan-400/20"
              }`}
              aria-label="Enviar"
            >
              <Send className="h-[18px] w-[18px] shrink-0" />
            </button>
            </div>
            )}
          </div>
          {isDictating || attachedPdf || attachedImage ? (
          <p className={`mt-1.5 break-words text-left text-[9px] leading-snug ${embedded ? "text-[var(--studio-hint)]" : "text-cyan-700"}`}>
            {isDictating
              ? "🎤 Dictando en vivo… clic en el mic para detener"
              : attachedPdf
                ? "PDF listo — envía para que CED lo lea y responda"
                : imageActionHint(imageMode)}
          </p>
          ) : null}
        </footer>
        </SplitPortal>
        {composerActions ? (
        <SplitPortal target={composerActions}>
            <AttachMenuButton
              clipOnly
              onPdfSelected={(file) => {
                setAttachedPdf(file);
                setAttachedImage(null);
                setImageMode("analyze");
              }}
              onImageSelected={(file, preview) => {
                setAttachedImage({ file, preview });
                setAttachedPdf(null);
                setImageMode((prev) =>
                  prev === "analyze" && recentMessagesAwaitPublish(messages)
                    ? "publish"
                    : prev,
                );
              }}
              disabled={busy || status?.blocked || !!attachedImage || !!attachedPdf}
            />
            <MicButton
              getBaseText={() => input}
              onTextUpdate={handleDictationText}
              onDictatingChange={handleDictatingChange}
              onLevel={setDictationLevel}
              disabled={status?.blocked}
            />
            <button
              type="button"
              disabled={
                busy ||
                (!input.trim() && !attachedImage && !attachedPdf) ||
                status?.blocked
              }
              onPointerDown={(e) => {
                e.preventDefault();
                keepInputFocusRef.current = true;
              }}
              onClick={() => void submit()}
              className={`box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px] ${
                embedded
                  ? "bg-sky-500 text-white shadow-[0_0_12px_rgba(59,183,255,0.45)] hover:bg-sky-400"
                  : "border border-cyan-400/60 bg-cyan-400/10 text-cyan-300 hover:bg-cyan-400/20"
              }`}
              aria-label="Enviar"
            >
              <Send className="h-[18px] w-[18px] shrink-0" />
            </button>
        </SplitPortal>
        ) : null}
      </div>
  );

  if (embedded) {
    return shell;
  }

  return (
    <div className="fixed inset-0 z-[150] flex items-end justify-center overflow-x-hidden bg-black/50 p-0 backdrop-blur-[1px] sm:items-center sm:p-4">
      {shell}
    </div>
  );
}
