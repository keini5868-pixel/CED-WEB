"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { SwitchCamera } from "lucide-react";

type CedCameraPreviewProps = {
  stream: MediaStream | null;
  active: boolean;
  facing?: "user" | "environment";
  onFlipCamera?: () => void;
  /** Superpone la vista al lienzo central (el orbe queda como núcleo). */
  overlay?: boolean;
};

/** Vista en vivo de la cámara — stream directo, sin snapshots JPEG. */
export function CedCameraPreview({
  stream,
  active,
  facing = "user",
  onFlipCamera,
  overlay = false,
}: CedCameraPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const visible = active && Boolean(stream);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return;
    video.srcObject = stream;
    void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  const chrome = visible ? (
    <>
      <div className="absolute inset-x-0 top-0 z-[1] flex items-center justify-between bg-gradient-to-b from-black/70 to-transparent px-3 py-2">
        <span className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold uppercase tracking-widest text-cyan-300 sm:text-xs">
          Vista para CED
        </span>
        <span className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wide text-cyan-400/80 sm:text-xs">
            {facing === "environment" ? "Trasera" : "Frontal"}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
            <span className="text-[10px] uppercase tracking-wide text-red-300/90 sm:text-xs">
              En vivo
            </span>
          </span>
        </span>
      </div>
      {onFlipCamera ? (
        <button
          type="button"
          onClick={onFlipCamera}
          title="Cambiar a cámara trasera"
          aria-label="Cambiar cámara frontal o trasera"
          className="absolute bottom-3 right-3 z-[1] flex h-10 w-10 items-center justify-center rounded-full border border-cyan-400/60 bg-black/70 text-cyan-200 shadow-lg transition hover:border-cyan-300 hover:bg-cyan-950/80 hover:text-cyan-100"
        >
          <SwitchCamera className="h-5 w-5" />
        </button>
      ) : null}
    </>
  ) : null;

  const video = (
    <video
      id="ced-camera-feed"
      ref={videoRef}
      autoPlay
      playsInline
      muted
      className={
        overlay
          ? "h-full w-full object-cover"
          : "aspect-[4/3] w-full object-cover"
      }
    />
  );

  if (overlay) {
    return (
      <div
        className={
          visible
            ? "absolute inset-0 z-[5] overflow-hidden rounded-xl border border-cyan-400/50 bg-black/80"
            : "pointer-events-none invisible absolute inset-0 z-0 overflow-hidden"
        }
        aria-hidden={!visible}
      >
        {video}
        {chrome}
      </div>
    );
  }

  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          initial={{ opacity: 0, y: 10, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.25 }}
          className="mt-4 w-full max-w-[min(92vw,520px)]"
        >
          <div className="relative overflow-hidden rounded-xl border border-cyan-400/50 bg-black/80 ced-panel-glow shadow-[0_0_24px_rgba(0,229,255,0.15)]">
            {video}
            {chrome}
          </div>
        </motion.div>
      ) : (
        <div className="pointer-events-none absolute h-px w-px overflow-hidden opacity-0" aria-hidden>
          {video}
        </div>
      )}
    </AnimatePresence>
  );
}
