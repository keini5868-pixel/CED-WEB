"use client";

import { useEffect, useState } from "react";

import { HudCarouselCard } from "@/components/dashboard/carousel/HudCarouselCard";
import type { CarouselCardData } from "@/components/dashboard/carousel/types";

interface CarouselMobileStripProps {
  cards: CarouselCardData[];
}

/** Móvil / tablet: carrusel 2D horizontal (sin WebGL). */
export function CarouselMobileStrip({ cards }: CarouselMobileStripProps) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % cards.length);
    }, 5000);
    return () => clearInterval(id);
  }, [cards.length]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2">
        {cards.map((card, i) => (
          <div key={card.id} className="shrink-0 snap-center">
            <HudCarouselCard card={card} compact />
            {i === index ? (
              <p className="mt-1 text-center text-[9px] text-cyan-600">●</p>
            ) : (
              <p className="mt-1 text-center text-[9px] text-zinc-700">○</p>
            )}
          </div>
        ))}
      </div>
      <p className="ced-hud-text-secondary text-center text-[10px]">
        Desliza · {index + 1}/{cards.length}
      </p>
    </div>
  );
}
