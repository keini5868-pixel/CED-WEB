"use client";

import { useEffect, useRef, useState } from "react";

const SMOOTHING = 0.35;
/** React no debe re-renderizar a 60fps — solo lo necesario para el orbe. */
const STATE_COMMIT_MS = 66;

/**
 * Nivel de audio 0–1 desde MediaStream (mic o altavoz).
 * El loop de análisis vive en refs + rAF; setState va throttled.
 */
export function useAudioAnalyser(stream: MediaStream | null, enabled: boolean) {
  const [level, setLevel] = useState(0);
  const levelRef = useRef(0);
  const rafRef = useRef(0);
  const lastCommitRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const teardown = () => {
      cancelled = true;
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = 0;
      }
    };

    if (!enabled || !stream) {
      teardown();
      levelRef.current = 0;
      setLevel((prev) => (prev === 0 ? prev : 0));
      return teardown;
    }

    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = (now: number) => {
      if (cancelled) return;

      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) sum += data[i] ?? 0;
      const avg = sum / data.length / 255;
      levelRef.current = levelRef.current * (1 - SMOOTHING) + avg * SMOOTHING;

      if (now - lastCommitRef.current >= STATE_COMMIT_MS) {
        lastCommitRef.current = now;
        const next = levelRef.current;
        setLevel((prev) =>
          Math.abs(prev - next) < 0.002 ? prev : next,
        );
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    void (async () => {
      try {
        if (ctx.state === "suspended") await ctx.resume();
      } catch {
        /* ignore */
      }
      if (cancelled) {
        ctx.close().catch(() => undefined);
        return;
      }

      lastCommitRef.current = performance.now();
      rafRef.current = requestAnimationFrame(tick);
    })();

    return () => {
      teardown();
      ctx.close().catch(() => undefined);
      levelRef.current = 0;
      setLevel((prev) => (prev === 0 ? prev : 0));
    };
  }, [stream, enabled]);

  return level;
}
