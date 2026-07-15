"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";

type Props = {
  url: string | null;
  prompt?: string;
  onDismiss?: () => void;
};

/** Vista previa compacta bajo el orbe — la conversación principal va en el panel derecho. */
export function CedVoiceImagePreview({
  url,
  prompt,
  onDismiss,
}: Props) {
  const src = url ? normalizeCedMediaUrl(url) : null;
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const label = prompt ? `Imagen: ${prompt}` : "Imagen generada por CED";

  return (
    <AnimatePresence>
      {src ? (
        <motion.div
          key={src}
          initial={{ opacity: 0, y: 12, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          className="mt-4 w-full max-w-sm"
        >
          <div className="overflow-hidden rounded-xl border border-cyan-500/40 bg-black/60 shadow-[0_0_24px_rgba(0,229,255,0.15)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={src}
              alt={label}
              className="max-h-72 w-full cursor-zoom-in object-contain transition hover:opacity-95"
              onClick={() => setLightboxOpen(true)}
              onError={(e) => {
                e.currentTarget.alt = "No se pudo cargar la imagen";
              }}
            />
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
