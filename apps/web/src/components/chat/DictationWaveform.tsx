"use client";

import { useEffect, useRef } from "react";

const BAR_COUNT = 52;

/**
 * Línea de nivel mientras se dicta — se mueve con la voz, queda baja en silencio.
 */
export function DictationWaveform({
  level,
  active,
}: {
  level: number;
  active: boolean;
}) {
  const barsRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<number[]>(Array.from({ length: BAR_COUNT }, () => 0.1));

  useEffect(() => {
    if (!active) {
      historyRef.current = Array.from({ length: BAR_COUNT }, () => 0.1);
      const root = barsRef.current;
      if (root) {
        for (let i = 0; i < root.children.length; i += 1) {
          (root.children[i] as HTMLElement).style.height = "18%";
        }
      }
      return;
    }
    const next = Math.min(1, Math.max(0.08, level * 3.4));
    const hist = historyRef.current;
    hist.shift();
    hist.push(next);
    const root = barsRef.current;
    if (!root) return;
    for (let i = 0; i < hist.length; i += 1) {
      const el = root.children[i] as HTMLElement | undefined;
      if (el) el.style.height = `${Math.round(hist[i]! * 100)}%`;
    }
  }, [level, active]);

  if (!active) return null;

  return (
    <div
      className="flex h-5 w-full items-center gap-px px-1"
      aria-hidden
      title="Grabando audio"
    >
      <div ref={barsRef} className="flex h-full w-full items-center gap-px">
        {Array.from({ length: BAR_COUNT }, (_, i) => (
          <span
            key={i}
            className="inline-block w-[2px] flex-1 rounded-full bg-cyan-400/90"
            style={{ height: "18%" }}
          />
        ))}
      </div>
    </div>
  );
}
