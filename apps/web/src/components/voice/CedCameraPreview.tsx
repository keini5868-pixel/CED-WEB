"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";

type CedCameraPreviewProps = {
  stream: MediaStream | null;
  active: boolean;
};

/** Vista en vivo de la cámara — stream directo, sin snapshots JPEG. */
export function CedCameraPreview({ stream, active }: CedCameraPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return;
    video.srcObject = stream;
    void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  return (
    <AnimatePresence>
      {active && stream ? (
        <motion.div
          initial={{ opacity: 0, y: 10, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.25 }}
          className="mt-4 w-full max-w-[min(92vw,520px)]"
        >
          <div className="relative overflow-hidden rounded-xl border border-cyan-400/50 bg-black/80 ced-panel-glow shadow-[0_0_24px_rgba(0,229,255,0.15)]">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="aspect-[4/3] w-full object-cover"
            />
            <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between bg-gradient-to-b from-black/70 to-transparent px-3 py-2">
              <span className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold uppercase tracking-widest text-cyan-300 sm:text-xs">
                Vista para CED
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                <span className="text-[10px] uppercase tracking-wide text-red-300/90 sm:text-xs">
                  En vivo
                </span>
              </span>
            </div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
