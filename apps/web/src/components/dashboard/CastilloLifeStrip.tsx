"use client";

import { useHudLifeData } from "@/hooks/useHudLifeData";

export function CastilloLifeStrip() {
  const { castilloStripText } = useHudLifeData();
  const text = castilloStripText();
  const marquee = text.length > 38;

  return (
    <div className="ced-hud-text-secondary mb-2 shrink-0 overflow-hidden text-[10px] text-cyan-400/70">
      <div
        className={[
          "flex gap-3 whitespace-nowrap py-0.5",
          marquee ? "ced-castillo-life-strip" : "",
        ].join(" ")}
      >
        <span>{text}</span>
        {marquee ? <span aria-hidden>{text}</span> : null}
      </div>
    </div>
  );
}
