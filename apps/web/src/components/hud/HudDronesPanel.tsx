"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState, useEffect } from "react";

import { useHudFeed } from "@/contexts/HudFeedContext";
import { useHudPanels } from "@/contexts/HudPanelContext";
import { useHudIntelStream } from "@/hooks/useHudIntelStream";
import { useUsageBalance } from "@/hooks/useUsageBalance";

function Crosshair({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      className={className}
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
    >
      <circle cx="20" cy="20" r="14" className="text-cyan-500/40" />
      <line x1="20" y1="4" x2="20" y2="36" className="text-cyan-400/70" />
      <line x1="4" y1="20" x2="36" y2="20" className="text-cyan-400/70" />
      <circle cx="20" cy="20" r="2" fill="currentColor" className="text-cyan-300" />
    </svg>
  );
}

const KIND_LABEL: Record<string, string> = {
  voice: "VOZ",
  news: "NOTICIA",
  stat: "STATS",
  report: "INFORME",
};

export function HudDronesPanel() {
  const { streamConnected } = useHudPanels();
  useHudIntelStream(!streamConnected);
  const { items, marqueeText } = useHudFeed();
  const { drones } = useHudPanels();
  const { balance } = useUsageBalance(5000);
  const [cardIndex, setCardIndex] = useState(0);

  const cards = useMemo(() => {
    const usageCard = {
      id: "usage-live",
      kind: "stat" as const,
      text: `Uso voz hoy: ${balance.used.toFixed(1)} / ${balance.plan} min (${balance.percent.toFixed(0)}%)`,
    };
    const fromPanels = drones.slice(0, 8).map((d) => ({
      id: d.id,
      kind: "news" as const,
      text: d.text || d.title,
    }));
    const fromFeed = items.slice(0, 8).map((i) => ({
      id: i.id,
      kind: i.kind,
      text: i.text,
    }));
    const merged = [...fromPanels, ...fromFeed];
    const unique = merged.filter(
      (c, i, arr) => arr.findIndex((x) => x.text === c.text) === i,
    );
    return [usageCard, ...unique].slice(0, 14);
  }, [items, drones, balance.used, balance.plan, balance.percent]);

  useEffect(() => {
    if (cards.length < 2) return;
    const id = setInterval(() => {
      setCardIndex((i) => (i + 1) % cards.length);
    }, 6000);
    return () => clearInterval(id);
  }, [cards.length]);

  const active = cards[cardIndex] ?? cards[0];

  return (
    <div className="relative flex min-h-[140px] flex-col overflow-hidden">
      <div className="relative z-20 shrink-0 overflow-hidden border-b border-cyan-900/40 py-2">
        <div className="ced-hud-marquee flex whitespace-nowrap">
          <span className="ced-hud-marquee-track ced-hud-text-accent px-2 text-xs tracking-wide">
            {marqueeText}
            {"  ·  "}
            {marqueeText}
          </span>
        </div>
      </div>

      <div className="relative min-h-[100px] flex-1">
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="ced-hud-radar-ring absolute h-28 w-28 rounded-full border border-cyan-500/25" />
          <div className="ced-hud-radar-ring-reverse absolute h-20 w-20 rounded-full border border-dashed border-cyan-400/35" />
          <div className="absolute h-12 w-12 rounded-full border border-cyan-400/50 bg-cyan-950/20 ced-panel-glow" />
          <span className="absolute font-[family-name:var(--font-orbitron)] text-[9px] tracking-[0.35em] text-cyan-600/80">
            AI CORE
          </span>
        </div>

        <Crosshair className="absolute left-3 top-10 h-8 w-8 text-cyan-400/60" />
        <Crosshair className="absolute bottom-6 left-1/4 h-7 w-7 text-cyan-500/50" />
        <Crosshair className="absolute right-4 top-12 h-9 w-9 text-cyan-400/55" />

        <div className="absolute bottom-2 left-0 right-0 z-20 px-3">
          <AnimatePresence mode="wait">
            {active ? (
              <motion.div
                key={active.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.35 }}
                className="rounded border border-cyan-800/50 bg-[#0a0a0a]/90 px-2 py-1.5"
              >
                <span className="font-[family-name:var(--font-orbitron)] text-[10px] text-cyan-500">
                  {KIND_LABEL[active.kind] ?? "CED"}
                </span>
                <p className="ced-hud-text-body mt-0.5 line-clamp-2 text-xs leading-snug">
                  {active.text}
                </p>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
