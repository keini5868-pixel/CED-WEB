"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";

type Props = {
  url: string | null;
  prompt?: string;
  /** Cambia en cada generación para forzar recarga aunque la URL se parezca. */
  shownAt?: number;
  onDismiss?: () => void;
  /** Superpone la imagen al lienzo central. */
  overlay?: boolean;
  generating?: boolean;
};

/** Vista previa de imagen — en overlay cubre el núcleo; si no, queda bajo el orbe. */
export function CedVoiceImagePreview({
  url,
  prompt,
  shownAt,
  onDismiss,
  overlay = false,
  generating = false,
}: Props) {
  const src = url ? normalizeCedMediaUrl(url) : null;
  const frameKey = src ? `${src}#${shownAt ?? 0}` : generating ? "generating" : "empty";
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const label = prompt ? `Imagen: ${prompt}` : "Imagen generada por CED";

  if (generating && !src) {
    return (
      <div
        className={
          overlay
            ? "absolute inset-0 z-[4] flex flex-col items-center justify-center overflow-hidden rounded-xl border border-cyan-400/50 bg-black/85"
            : "mt-4 flex w-full max-w-sm flex-col items-center justify-center rounded-xl border border-cyan-400/50 bg-black/70 px-4 py-8"
        }
      >
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-300/30 border-t-cyan-300" />
        <p className="mt-2 text-center font-[family-name:var(--font-orbitron)] text-[8px] tracking-widest text-cyan-200 lg:text-[10px]">
          GENERANDO IMAGEN
        </p>
      </div>
    );
  }

  return (
    <AnimatePresence>
      {src ? (
        <motion.div
          key={frameKey}
          initial={{ opacity: 0, y: overlay ? 0 : 12, scale: overlay ? 1 : 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: overlay ? 0 : 8, scale: 0.98 }}
          className={
            overlay
              ? "absolute inset-0 z-[4] overflow-hidden rounded-xl border border-cyan-500/40 bg-black/80"
              : "mt-4 w-full max-w-sm"
          }
        >
          <div
            className={
              overlay
                ? "flex h-full flex-col overflow-hidden"
                : "overflow-hidden rounded-xl border border-cyan-500/40 bg-black/60 shadow-[0_0_24px_rgba(0,229,255,0.15)]"
            }
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <div className="relative min-h-0 flex-1">
            <img
              src={src}
              alt={label}
              className={
                overlay
                  ? `min-h-0 w-full flex-1 cursor-zoom-in object-contain transition ${generating ? "opacity-40" : "hover:opacity-95"}`
                  : `max-h-72 w-full cursor-zoom-in object-contain transition ${generating ? "opacity-40" : "hover:opacity-95"}`
              }
              onClick={() => setLightboxOpen(true)}
              onError={(e) => {
                e.currentTarget.alt = "No se pudo cargar la imagen";
              }}
            />
            {generating ? (
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center bg-black/45">
                <span className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-300/30 border-t-cyan-300" />
                <p className="mt-2 font-[family-name:var(--font-orbitron)] text-[8px] tracking-widest text-cyan-200 lg:text-[10px]">
                  GENERANDO IMAGEN
                </p>
              </div>
            ) : null}
            </div>
            <div className="flex items-center justify-between gap-2 px-3 py-2">
              <p className="ced-hud-text-secondary truncate text-xs">
                {prompt ? `Imagen: ${prompt}` : "Imagen generada"}
              </p>
              {onDismiss ? (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="shrink-0 text-xs text-cyan-400/80 hover:text-cyan-300"
                >
                  Cerrar
                </button>
              ) : null}
            </div>
          </div>
          <ImageLightbox
            src={src}
            alt={label}
            open={lightboxOpen}
            onClose={() => setLightboxOpen(false)}
          />
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
