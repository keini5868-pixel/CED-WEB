"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { CastilloLifeStrip } from "@/components/dashboard/CastilloLifeStrip";
import { CarouselMobileStrip } from "@/components/dashboard/carousel/CarouselMobileStrip";
import {
  CAROUSEL_HEIGHT_PX,
  CAROUSEL_ROTATION_SPEED,
} from "@/components/dashboard/carousel/carouselLayout";
import type { CarouselCardData } from "@/components/dashboard/carousel/types";
import { useCarouselRotation } from "@/components/dashboard/carousel/useCarouselRotation";
import { HUD_BACKGROUND } from "@/lib/hud/hudBackgroundConfig";
import { fetchHudCarousel } from "@/lib/api/hud";
import { getMockCarouselSnapshot } from "@/components/dashboard/carousel/mockCarouselData";

const CarouselScene = dynamic(
  () =>
    import("@/components/dashboard/carousel/CarouselScene").then(
      (m) => m.CarouselScene,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="ced-carousel-stage flex h-full min-h-[320px] items-center justify-center">
        <span className="font-[family-name:var(--font-orbitron)] text-xs text-cyan-700">
          CARGANDO CARRUSEL…
        </span>
      </div>
    ),
  },
);

const REFRESH_MS = HUD_BACKGROUND.carouselRefreshMs;
const INITIAL_DELAY_MS = HUD_BACKGROUND.carouselInitialDelayMs;

/** Fase 3A/3B — carrusel 3D HUD (API + fallback mock). */
export function LeftPanel3DCarousel() {
  const [cards, setCards] = useState<CarouselCardData[]>(
    () => getMockCarouselSnapshot().cards,
  );
  const [prospectionMode, setProspectionMode] = useState(false);
  const baseSpeed = prospectionMode
    ? CAROUSEL_ROTATION_SPEED * 1.35
    : CAROUSEL_ROTATION_SPEED;
  const { pause, resume, rotationSpeed } = useCarouselRotation(baseSpeed);

  const load = useCallback(async () => {
    const snapshot = await fetchHudCarousel();
    if (snapshot?.cards?.length) {
      setCards(snapshot.cards);
      setProspectionMode(Boolean(snapshot.prospectionMode));
    }
  }, []);

  useEffect(() => {
    const initial = setTimeout(() => void load(), INITIAL_DELAY_MS);
    const id = setInterval(() => void load(), REFRESH_MS);
    return () => {
      clearTimeout(initial);
      clearInterval(id);
    };
  }, [load]);

  return (
    <>
      <div className="hidden shrink-0 flex-col lg:flex">
        <p className="ced-hud-text-secondary shrink-0 text-[10px] uppercase tracking-widest">
          Castillo · intel en vivo
          {prospectionMode ? (
            <span className="ml-2 text-red-400">· PROSPECCIÓN</span>
          ) : null}
        </p>
        <CastilloLifeStrip />
        <div
          className="relative shrink-0 overflow-hidden"
          style={{ height: CAROUSEL_HEIGHT_PX, maxHeight: CAROUSEL_HEIGHT_PX }}
        >
          <CarouselScene
            cards={cards}
            rotationSpeed={rotationSpeed}
            heightPx={CAROUSEL_HEIGHT_PX}
            onPointerEnter={pause}
            onPointerLeave={resume}
          />
        </div>
      </div>
      <div className="lg:hidden">
        <p className="ced-hud-text-secondary shrink-0 text-[10px] uppercase tracking-widest">
          Castillo · intel en vivo
        </p>
        <CastilloLifeStrip />
        <CarouselMobileStrip cards={cards} />
      </div>
    </>
  );
}
