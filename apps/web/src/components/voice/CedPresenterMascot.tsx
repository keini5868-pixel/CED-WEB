"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef } from "react";

type Props = {
  visible: boolean;
  audioStream: MediaStream | null;
};

function useStreamLevel(stream: MediaStream | null) {
  const levelRef = useRef(0);

  useEffect(() => {
    if (!stream) {
      levelRef.current = 0;
      return;
    }
    let raf = 0;
    let ctx: AudioContext | null = null;
    const AC =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    ctx = new AC();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    const src = ctx.createMediaStreamSource(stream);
    src.connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const n = ((data[i] ?? 128) - 128) / 128;
        sum += n * n;
      }
      const rms = Math.min(1, Math.sqrt(sum / data.length) * 6);
      levelRef.current += (rms - levelRef.current) * 0.28;
      raf = requestAnimationFrame(tick);
    };
    void ctx.resume().then(() => {
      raf = requestAnimationFrame(tick);
    });
    return () => {
      cancelAnimationFrame(raf);
      void ctx?.close();
      levelRef.current = 0;
    };
  }, [stream]);

  return levelRef;
}

/** Holograma vivo — el robot de la foto, flotando y reaccionando a la voz. */
export function CedPresenterMascot({ visible, audioStream }: Props) {
  const levelRef = useStreamLevel(visible ? audioStream : null);
  const spriteRef = useRef<HTMLDivElement>(null);
  const scanRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!visible) return;
    let raf = 0;
    const t0 = performance.now();
    const loop = (now: number) => {
      const t = (now - t0) / 1000;
      const level = levelRef.current;
      const talking = level > 0.08;
      const bob = Math.sin(t * 1.7) * 8 + Math.sin(t * 0.9) * 3;
      const talk = talking ? Math.sin(t * 11) * (5 + level * 14) : Math.sin(t * 2.4) * 2;
      const rotY = Math.sin(t * 1.05) * 14 + (talking ? Math.sin(t * 4.2) * 18 * level : 0);
      const rotZ = Math.sin(t * 0.8) * 2.4 + (talking ? Math.sin(t * 6) * 5 * level : 0);
      const rotX = talking ? Math.sin(t * 8) * 4 * level : Math.sin(t * 0.6) * 1.5;
      const scale = 1 + level * 0.08 + (talking ? Math.abs(Math.sin(t * 14)) * 0.03 : 0);
      const flick = 0.88 + Math.sin(t * 31) * 0.07 + Math.sin(t * 8.5) * 0.05;
      const el = spriteRef.current;
      if (el) {
        el.style.transform = `translateY(${bob + talk}px) rotateX(${rotX}deg) rotateY(${rotY}deg) rotateZ(${rotZ}deg) scale(${scale})`;
        el.style.filter = `brightness(${flick}) contrast(1.08) drop-shadow(0 0 18px rgba(0,229,255,0.55))`;
      }
      const scan = scanRef.current;
      if (scan) {
        scan.style.opacity = String(0.18 + level * 0.35);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [visible, levelRef]);

  return (
    <div
      className="pointer-events-none absolute inset-0 z-[79] flex items-center justify-center overflow-hidden pr-[6.5rem] sm:pr-[8rem] lg:pr-[min(15.5rem,28vw)]"
      aria-hidden
    >
      <AnimatePresence>
        {visible ? (
          <motion.div
            key="ced-holo-bot"
            className="relative translate-y-[6%]"
            style={{ perspective: 720 }}
            initial={{ opacity: 0, y: 36, scale: 0.45, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: 18, scale: 0.72, filter: "blur(8px)" }}
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="ced-holo-bot-dust" />
            <div
              ref={spriteRef}
              className="relative will-change-transform"
              style={{ transformStyle: "preserve-3d" }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/voice/holo-bot.png?v=2"
                alt=""
                className="h-[11.5rem] w-auto select-none sm:h-[13.5rem] lg:h-[15.5rem]"
                draggable={false}
              />
              <div ref={scanRef} className="ced-holo-bot-scan" />
              <div className="ced-holo-bot-glitch" />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
