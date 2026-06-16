"use client";

import { AnimatePresence, motion } from "framer-motion";

import { normalizeCedMediaUrl } from "@/lib/api/media-url";

type Props = {
  url: string | null;
  prompt?: string;
  onOpenChat?: () => void;
  onDismiss?: () => void;
};

/** Vista previa de imagen generada por voz — visible sin abrir el chat manualmente. */
export function CedVoiceImagePreview({
  url,
  prompt,
  onOpenChat,
  onDismiss,
}: Props) {
  const src = url ? normalizeCedMediaUrl(url) : null;

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
            <button
              type="button"
              onClick={onOpenChat}
              className="block w-full cursor-pointer"
              aria-label="Abrir imagen en chat"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={prompt ? `Imagen: ${prompt}` : "Imagen generada por CED"}
                className="max-h-72 w-full object-contain"
                onError={(e) => {
                  e.currentTarget.alt = "No se pudo cargar la imagen";
                }}
              />
            </button>
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
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
