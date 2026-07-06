"use client";

import { useHudLifeData } from "@/hooks/useHudLifeData";

export function CastilloLifeStrip() {
  const { castilloStripText } = useHudLifeData();
  const text = castilloStripText();

  return (
    <div className="ced-hud-text-secondary mb-2 shrink-0 overflow-hidden py-0.5 text-[10px] text-cyan-400/70">
      <span className="life-marquee inline-block min-w-full">{text}</span>
    </div>
  );
}
