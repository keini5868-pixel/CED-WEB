"use client";

import type {
  CarouselCardAccent,
  CarouselCardData,
} from "@/components/dashboard/carousel/types";
import {
  CARD_HEIGHT_COMPACT_PX,
  CARD_HEIGHT_PX,
  CARD_WIDTH_COMPACT_PX,
  CARD_WIDTH_PX,
} from "@/components/dashboard/carousel/carouselLayout";

const ACCENT_BORDER: Record<CarouselCardAccent, string> = {
  cyan: "border-cyan-400/70 shadow-[0_0_18px_rgba(0,229,255,0.25)]",
  pink: "border-pink-400/70 shadow-[0_0_18px_rgba(244,114,182,0.25)]",
  red: "border-red-400/80 shadow-[0_0_20px_rgba(248,113,113,0.35)]",
  orange: "border-orange-400/70 shadow-[0_0_18px_rgba(251,146,60,0.25)]",
  gold: "border-amber-400/70 shadow-[0_0_18px_rgba(251,191,36,0.25)]",
  green: "border-emerald-400/70 shadow-[0_0_18px_rgba(52,211,153,0.25)]",
};

const ACCENT_TITLE: Record<CarouselCardAccent, string> = {
  cyan: "text-cyan-300",
  pink: "text-pink-300",
  red: "text-red-300",
  orange: "text-orange-300",
  gold: "text-amber-300",
  green: "text-emerald-300",
};

interface HudCarouselCardProps {
  card: CarouselCardData;
  compact?: boolean;
}

/** Tarjeta HUD — HTML overlay en carrusel 3D o strip móvil. */
export function HudCarouselCard({ card, compact }: HudCarouselCardProps) {
  const w = compact ? CARD_WIDTH_COMPACT_PX : CARD_WIDTH_PX;
  const h = compact ? CARD_HEIGHT_COMPACT_PX : CARD_HEIGHT_PX;

  return (
    <div
      className={`relative flex flex-col rounded-sm border bg-[#0a0a0acc] p-4 backdrop-blur-sm ${ACCENT_BORDER[card.accent]}`}
      style={{ width: w, height: h }}
    >
      <span className="pointer-events-none absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-current opacity-60" />
      <span className="pointer-events-none absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-current opacity-60" />
      <span className="pointer-events-none absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-current opacity-60" />
      <span className="pointer-events-none absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-current opacity-60" />

      <div className="mb-2 flex items-center gap-2">
        {card.badge ? <span className="text-base">{card.badge}</span> : null}
        <h3
          className={`font-[family-name:var(--font-orbitron)] text-[15px] font-bold tracking-[0.14em] ${ACCENT_TITLE[card.accent]}`}
        >
          {card.title}
        </h3>
      </div>

      <div className="flex flex-1 flex-col justify-center gap-1.5">
        {card.lines.map((line, index) => (
          <p
            key={`${card.id}-line-${index}`}
            className="ced-hud-text-body text-[17px] font-medium leading-snug text-zinc-100"
          >
            {line}
          </p>
        ))}
      </div>

      {card.footer ? (
        <p className="mt-2 text-[11px] uppercase tracking-wider text-zinc-500">
          {card.footer}
        </p>
      ) : null}
    </div>
  );
}
