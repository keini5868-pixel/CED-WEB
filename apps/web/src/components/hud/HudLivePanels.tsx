"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { HudPanel } from "@ced/ui";

import { useHudFeed, type HudFeedItem } from "@/contexts/HudFeedContext";
import { downloadGeneratedImage } from "@/lib/api/image-download";
import { postVoiceChatImage, deleteVoiceChatImage } from "@/lib/api/voiceClient";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";

function roleLabel(kind: HudFeedItem["kind"], item?: HudFeedItem): string {
  if (kind === "image" && item?.role === "user") return "Usted · Imagen";
  if (kind === "voice") return "Usted";
  if (kind === "image") return "CED · Imagen";
  if (kind === "report") return "CED";
  if (kind === "news") return "Intel";
  return "CED";
}

function formatFileSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTranscript(items: HudFeedItem[]): string {
  const chronological = [...items].reverse();
  return chronological
    .map((item) => {
      if (item.kind === "image" && item.imageUrl) {
        return `${roleLabel(item.kind, item)}: [Imagen] ${item.text} ${item.imageUrl}`;
      }
      return `${roleLabel(item.kind, item)}: ${item.text}`;
    })
    .join("\n\n");
}

function HudTranscriptImage({
  item,
  onExpand,
  onRemove,
}: {
  item: HudFeedItem;
  onExpand: (url: string) => void;
  onRemove?: (id: string) => void;
}) {
  const src = normalizeCedMediaUrl(item.imageUrl ?? "");
  const [busy, setBusy] = useState(false);

  if (!src && item.uploadStatus !== "uploading") return null;

  return (
    <div className="mt-2 space-y-2">
      {src ? (
        <button
          type="button"
          onClick={() => onExpand(src)}
          className="block overflow-hidden rounded-lg border border-cyan-500/30 transition hover:border-cyan-400/60"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={item.imagePrompt || item.text || "Imagen CED"}
            className="max-h-48 w-full object-cover"
          />
        </button>
      ) : (
        <div className="rounded-lg border border-dashed border-cyan-500/30 bg-cyan-950/20 px-3 py-8 text-center text-xs text-cyan-400">
          Subiendo imagen…
        </div>
      )}
      {(item.fileName || item.fileSize) && (
        <p className="ced-hud-text-muted text-[10px]">
          {item.fileName}
          {item.fileSize ? ` · ${formatFileSize(item.fileSize)}` : ""}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {src ? (
          <>
            <button
              type="button"
              onClick={() => onExpand(src)}
              className="rounded border border-cyan-500/40 px-2 py-1 text-[10px] uppercase tracking-wider text-cyan-300"
            >
              Ver en grande
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                void downloadGeneratedImage(src, item.imagePrompt).finally(() =>
                  setBusy(false),
                );
              }}
              className="rounded border border-cyan-500/40 px-2 py-1 text-[10px] uppercase tracking-wider text-cyan-300 disabled:opacity-50"
            >
              {busy ? "Descargando…" : "Descargar"}
            </button>
          </>
        ) : null}
        {onRemove && item.role === "user" ? (
          <button
            type="button"
            onClick={() => onRemove(item.id)}
            className="rounded border border-red-500/40 px-2 py-1 text-[10px] uppercase tracking-wider text-red-300"
          >
            Quitar
          </button>
        ) : null}
      </div>
    </div>
  );
}

function HudVoiceImageUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { pushVoiceImage, updateVoiceImage } = useHudFeed();

  const onFile = useCallback(
    async (file: File | null) => {
      if (!file) return;
      setError(null);
      const maxBytes = 10 * 1024 * 1024;
      const allowed = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/heic",
        "image/heif",
      ];
      if (!allowed.includes(file.type) && !file.name.match(/\.(jpe?g|png|webp|gif|heic|heif)$/i)) {
        setError("Formato no soportado. Usa JPG, PNG, WebP o GIF.");
        return;
      }
      if (file.size > maxBytes) {
        setError("Imagen muy grande. Máximo 10 MB.");
        return;
      }

      const previewUrl = URL.createObjectURL(file);
      const itemId = pushVoiceImage(previewUrl, {
        fileName: file.name,
        fileSize: file.size,
        status: "uploading",
        role: "user",
      });

      setBusy(true);
      try {
        const reader = new FileReader();
        const dataUrl = await new Promise<string>((resolve, reject) => {
          reader.onload = () => resolve(String(reader.result ?? ""));
          reader.onerror = () => reject(new Error("No se pudo leer la imagen"));
          reader.readAsDataURL(file);
        });
        const result = await postVoiceChatImage({
          image_data: dataUrl,
          filename: file.name,
        });
        const serverUrl = normalizeCedMediaUrl(result.image_url || previewUrl);
        updateVoiceImage(itemId, {
          imageUrl: serverUrl,
          text: "Imagen lista para CED",
          uploadStatus: "ready",
          fileName: result.filename || file.name,
          fileSize: result.size_bytes ?? file.size,
        });
        URL.revokeObjectURL(previewUrl);
      } catch (e) {
        updateVoiceImage(itemId, {
          text: "Error al subir imagen",
          uploadStatus: "error",
        });
        setError(e instanceof Error ? e.message : "Error al subir imagen");
      } finally {
        setBusy(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [pushVoiceImage, updateVoiceImage],
  );

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif"
        className="hidden"
        onChange={(e) => void onFile(e.target.files?.[0] ?? null)}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className="rounded border border-cyan-500/40 px-2 py-1 font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-cyan-300 transition hover:border-cyan-400 disabled:opacity-40"
      >
        {busy ? "Subiendo…" : "📷 Subir imagen a CED"}
      </button>
      {error ? <p className="text-[10px] text-red-400">{error}</p> : null}
    </div>
  );
}

export function HudGlobalPanel() {
  const { voiceItems, removeVoiceImage } = useHudFeed();
  const [copied, setCopied] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);

  const transcript = useMemo(() => formatTranscript(voiceItems), [voiceItems]);
  const chronological = useMemo(() => [...voiceItems].reverse(), [voiceItems]);

  const handleRemoveImage = useCallback(
    (id: string) => {
      removeVoiceImage(id);
      void deleteVoiceChatImage().catch(() => undefined);
    },
    [removeVoiceImage],
  );

  const copyAll = useCallback(async () => {
    if (!transcript.trim()) return;
    try {
      await navigator.clipboard.writeText(transcript);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }, [transcript]);

  return (
    <div className="flex min-h-[280px] flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="ced-hud-text-secondary text-[10px] uppercase tracking-widest">
          Diálogo en vivo · {chronological.length} turnos
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <HudVoiceImageUpload />
          <button
            type="button"
            onClick={() => void copyAll()}
            disabled={!transcript.trim()}
            className="rounded border border-cyan-500/40 px-2 py-1 font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-cyan-300 transition hover:border-cyan-400 disabled:opacity-40"
          >
            {copied ? "Copiado" : "Copiar todo"}
          </button>
        </div>
      </div>

      {chronological.length === 0 ? (
        <div
          className="max-h-[min(420px,50vh)] flex-1 overflow-y-auto rounded border border-cyan-500/20 bg-black/40 p-3"
          role="log"
          aria-live="polite"
          aria-label="Transcripción de la conversación con CED"
        >
          <p className="ced-hud-text-body text-sm leading-relaxed">
            Aquí aparecerá la conversación con CED en tiempo real. Active el micrófono,
            suba imágenes para CED o genere imágenes por voz.
          </p>
        </div>
      ) : (
        <div
          className="max-h-[min(420px,50vh)] flex-1 overflow-y-auto rounded border border-cyan-500/20 bg-black/40 p-3"
          role="log"
          aria-live="polite"
          aria-label="Transcripción de la conversación con CED"
        >
          <div className="space-y-3">
            {chronological.map((item) => (
              <div key={item.id} className="group">
                <p className="font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-cyan-500/90">
                  {roleLabel(item.kind, item)}
                </p>
                {item.kind === "image" ? (
                  <>
                    <p className="ced-hud-text-body mt-1 text-sm text-cyan-100/90">{item.text}</p>
                    <HudTranscriptImage
                      item={item}
                      onExpand={setLightbox}
                      onRemove={item.role === "user" ? handleRemoveImage : undefined}
                    />
                  </>
                ) : (
                  <p className="ced-hud-text-body mt-1 select-text whitespace-pre-wrap text-sm leading-relaxed">
                    {item.text}
                  </p>
                )}
                {item.kind === "image" && item.imagePrompt ? (
                  <p className="ced-hud-text-secondary mt-1 text-xs">{item.imagePrompt}</p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {lightbox ? (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setLightbox(null)}
        >
          <button
            type="button"
            className="absolute right-4 top-4 rounded border border-cyan-500/50 px-3 py-1 text-sm text-cyan-200"
            onClick={() => setLightbox(null)}
          >
            Cerrar
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={lightbox}
            alt="Imagen ampliada"
            className="max-h-[90vh] max-w-full rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      ) : null}
    </div>
  );
}

export function HudSummaryPanel() {
  const { voiceItems } = useHudFeed();
  const lastReport = voiceItems.find((i) => i.kind === "report")?.text ?? "";

  return (
    <div className="space-y-2">
      <p className="ced-hud-text-secondary text-[10px] uppercase tracking-widest">
        Última respuesta CED
      </p>
      <p className="ced-hud-text-body whitespace-pre-wrap leading-relaxed">
        {lastReport || "La última respuesta de CED aparecerá aquí."}
      </p>
    </div>
  );
}

export function HudWavesPanel() {
  const { items } = useHudFeed();
  const stats = items.filter((i) => i.kind === "stat" || i.kind === "news").slice(0, 6);

  if (stats.length === 0) {
    return (
      <p className="ced-hud-text-body">
        Datos de búsquedas e intel aparecerán aquí durante la sesión.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {stats.map((item) => (
        <li key={item.id} className="border-l-2 border-amber-400/60 pl-3">
          <p className="ced-hud-text-body text-xs">{item.text}</p>
        </li>
      ))}
    </ul>
  );
}

export function HudGlobalPanelFrame({ children }: { children: React.ReactNode }) {
  return (
    <HudPanel title="CONVERSACIÓN" state="idle">
      {children}
    </HudPanel>
  );
}

export function HudSummaryPanelFrame({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <HudPanel title="ÚLTIMA RESPUESTA" state="idle">
      {children}
    </HudPanel>
  );
}
