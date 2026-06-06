"use client";

import { useCallback, useState } from "react";

import { CAROUSEL_ROTATION_SPEED } from "@/components/dashboard/carousel/carouselLayout";

export function useCarouselRotation(
  speed: number = CAROUSEL_ROTATION_SPEED,
) {
  const [paused, setPaused] = useState(false);

  const pause = useCallback(() => setPaused(true), []);
  const resume = useCallback(() => setPaused(false), []);

  return {
    paused,
    pause,
    resume,
    rotationSpeed: paused ? 0 : speed,
  };
}
