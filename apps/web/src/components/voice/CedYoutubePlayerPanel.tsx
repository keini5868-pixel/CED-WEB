"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play, X } from "lucide-react";

import {
  CED_YOUTUBE_EVENT,
  boostYoutubeEmbedAudio,
  buildYoutubeEmbedUrl,
  dispatchYoutubeMediaMode,
  parseYoutubePlayerState,
  postYoutubeCommand,
  postYoutubeListening,
  YT_STATE,
  type CedYoutubeAction,
  type CedYoutubeVideo,
} from "@/lib/voice/youtubePlayer";

/** Si tras cargar el embed no llega estado "playing" en este plazo, se asume autoplay bloqueado. */
const AUTOPLAY_GRACE_MS = 1800;

const hudControlBtn =
  "flex h-8 w-8 cursor-pointer items-center justify-center rounded border border-cyan-400/50 bg-cyan-400/5 text-[#00ffff] transition hover:bg-cyan-400/15";

/**
 * Mini-panel HUD flotante con el reproductor oficial de YouTube.
 * Recibe acciones del puente de voz vía CustomEvent `ced-youtube-event`
 * (emitidas por useCedVoiceSession al leer voice/client-state).
 *
 * Se porta a document.body con z > overlay de modo conducir (z-250),
 * porque el hub vive debajo de ese overlay y un z local no lo atraviesa.
 */
export function CedYoutubePlayerPanel() {
  const [video, setVideo] = useState<CedYoutubeVideo | null>(null);
  const [playerState, setPlayerState] = useState<number | null>(null);
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const playerStateRef = useRef<number | null>(null);
  const autoplayTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  const clearAutoplayTimer = useCallback(() => {
    if (autoplayTimerRef.current !== null) {
      window.clearTimeout(autoplayTimerRef.current);
      autoplayTimerRef.current = null;
    }
  }, []);

  const stopPlayback = useCallback(() => {
    postYoutubeCommand(iframeRef.current, "stopVideo");
  }, []);

  const setMediaMode = useCallback((active: boolean) => {
    dispatchYoutubeMediaMode(active);
  }, []);

  const close = useCallback(() => {
    stopPlayback();
    clearAutoplayTimer();
    setMediaMode(false);
    setVideo(null);
    setPlayerState(null);
    setAutoplayBlocked(false);
    playerStateRef.current = null;
  }, [stopPlayback, clearAutoplayTimer, setMediaMode]);

  useEffect(() => {
    const onBridgeAction = (ev: Event) => {
      const detail = (ev as CustomEvent<CedYoutubeAction>).detail;
      if (!detail) return;
      if (detail.action === "play") {
        setVideo((prev) => {
          if (prev?.videoId === detail.video.videoId) {
            postYoutubeCommand(iframeRef.current, "playVideo");
            boostYoutubeEmbedAudio(iframeRef.current);
            setMediaMode(true);
            return prev;
          }
          setPlayerState(null);
          setAutoplayBlocked(false);
          playerStateRef.current = null;
          return detail.video;
        });
        return;
      }
      if (detail.action === "pause") {
        postYoutubeCommand(iframeRef.current, "pauseVideo");
        setMediaMode(false);
        return;
      }
      if (detail.action === "resume") {
        postYoutubeCommand(iframeRef.current, "playVideo");
        boostYoutubeEmbedAudio(iframeRef.current);
        setMediaMode(true);
        return;
      }
      close();
    };
    window.addEventListener(CED_YOUTUBE_EVENT, onBridgeAction);
    return () => window.removeEventListener(CED_YOUTUBE_EVENT, onBridgeAction);
  }, [close, setMediaMode]);

  useEffect(() => {
    if (!video) return;
    const onMessage = (ev: MessageEvent) => {
      const state = parseYoutubePlayerState(ev);
      if (state === null) return;
      playerStateRef.current = state;
      setPlayerState(state);
      if (state === YT_STATE.playing || state === YT_STATE.buffering) {
        setAutoplayBlocked(false);
        boostYoutubeEmbedAudio(iframeRef.current);
        setMediaMode(true);
      } else if (state === YT_STATE.paused || state === YT_STATE.ended) {
        setMediaMode(false);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [video, setMediaMode]);

  useEffect(() => {
    if (!video) return;
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [video, close]);

  // Detener el video si el panel se desmonta con reproducción activa.
  useEffect(() => {
    return () => {
      stopPlayback();
      clearAutoplayTimer();
      dispatchYoutubeMediaMode(false);
    };
  }, [stopPlayback, clearAutoplayTimer]);

  const onIframeLoad = useCallback(() => {
    postYoutubeListening(iframeRef.current);
    boostYoutubeEmbedAudio(iframeRef.current);
    clearAutoplayTimer();
    autoplayTimerRef.current = window.setTimeout(() => {
      const state = playerStateRef.current;
      if (state !== YT_STATE.playing && state !== YT_STATE.buffering) {
        setAutoplayBlocked(true);
      } else {
        boostYoutubeEmbedAudio(iframeRef.current);
        setMediaMode(true);
      }
    }, AUTOPLAY_GRACE_MS);
  }, [clearAutoplayTimer, setMediaMode]);

  const isPlaying =
    playerState === YT_STATE.playing || playerState === YT_STATE.buffering;

  const togglePlayback = useCallback(() => {
    const willPause = playerStateRef.current === YT_STATE.playing;
    postYoutubeCommand(
      iframeRef.current,
      willPause ? "pauseVideo" : "playVideo",
    );
    if (!willPause) {
      boostYoutubeEmbedAudio(iframeRef.current);
      setMediaMode(true);
    } else {
      setMediaMode(false);
    }
    setAutoplayBlocked(false);
  }, [setMediaMode]);

  const embedUrl = video
    ? buildYoutubeEmbedUrl(
        video.videoId,
        typeof window !== "undefined" ? window.location.origin : undefined,
      )
    : null;

  const panel = (
    <AnimatePresence>
      {video && embedUrl ? (
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ duration: 0.2 }}
          aria-label="Reproductor de YouTube"
          className="fixed bottom-24 right-3 z-[260] w-[min(92vw,380px)] sm:right-5"
        >
          <div className="relative flex flex-col rounded-sm border border-cyan-400/70 bg-[#0a0a0acc] p-2 text-[#00ffff] shadow-[0_0_18px_rgba(0,229,255,0.25)] backdrop-blur-sm">
            <span className="pointer-events-none absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-current opacity-60" />
            <span className="pointer-events-none absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-current opacity-60" />
            <span className="pointer-events-none absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-current opacity-60" />
            <span className="pointer-events-none absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-current opacity-60" />

            <div className="mb-1.5 flex items-center gap-2 px-1">
              <div className="min-w-0 flex-1">
                <p className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-[0.18em] text-cyan-300">
                  ▶ YOUTUBE
                </p>
                <p
                  className="truncate text-[11px] text-cyan-100/90"
                  title={video.title || undefined}
                >
                  {video.title || "Video"}
                  {video.channelTitle ? (
                    <span className="text-cyan-400/60"> · {video.channelTitle}</span>
                  ) : null}
                </p>
              </div>
              <button
                type="button"
                className={hudControlBtn}
                aria-label={isPlaying ? "Pausar video" : "Reanudar video"}
                onClick={togglePlayback}
              >
                {isPlaying ? (
                  <Pause className="h-4 w-4" aria-hidden />
                ) : (
                  <Play className="h-4 w-4" aria-hidden />
                )}
              </button>
              <button
                type="button"
                className={hudControlBtn}
                aria-label="Cerrar reproductor de YouTube"
                onClick={close}
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>

            <div className="relative aspect-video w-full overflow-hidden rounded-sm border border-cyan-900/60 bg-black">
              <iframe
                key={video.videoId}
                ref={iframeRef}
                src={embedUrl}
                title={`YouTube: ${video.title || video.videoId}`}
                className="absolute inset-0 h-full w-full"
                allow="autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
                onLoad={onIframeLoad}
              />
              {autoplayBlocked && !isPlaying ? (
                <button
                  type="button"
                  onClick={togglePlayback}
                  aria-label="Reproducir video"
                  className="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-2 bg-black/70"
                >
                  <span className="flex h-12 w-12 items-center justify-center rounded-full border border-cyan-400/70 bg-cyan-400/10 shadow-[0_0_18px_rgba(0,229,255,0.35)]">
                    <Play className="h-6 w-6 text-[#00ffff]" aria-hidden />
                  </span>
                  <span className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.18em] text-cyan-300">
                    REPRODUCIR
                  </span>
                </button>
              ) : null}
            </div>
          </div>
        </motion.section>
      ) : null}
    </AnimatePresence>
  );

  if (!portalReady) return null;
  return createPortal(panel, document.body);
}
