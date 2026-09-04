"use client";

import { useEffect, useMemo } from "react";

import type { PresenterGesture } from "@/lib/voice/presenterGestures";

type Props = {
  gesture: PresenterGesture;
};

const SPRITE_VER = "photo2";

const SPRITES = {
  idle: `/voice/ced-puppet/idle.png?v=${SPRITE_VER}`,
  think: `/voice/ced-puppet/think.png?v=${SPRITE_VER}`,
  success: `/voice/ced-puppet/success.png?v=${SPRITE_VER}`,
  error: `/voice/ced-puppet/error.png?v=${SPRITE_VER}`,
  ok: `/voice/ced-puppet/ok.png?v=${SPRITE_VER}`,
  listen: `/voice/ced-puppet/listen.png?v=${SPRITE_VER}`,
  present: `/voice/ced-puppet/present.png?v=${SPRITE_VER}`,
} as const;

function spriteFor(gesture: PresenterGesture): string {
  switch (gesture) {
    case "think":
    case "construct":
    case "serious":
      return SPRITES.think;
    case "success":
    case "laugh":
      return SPRITES.success;
    case "error":
      return SPRITES.error;
    case "ok":
      return SPRITES.ok;
    case "listen":
    case "welcome":
    case "farewell":
      return SPRITES.listen;
    case "present":
    case "point":
    case "look":
      return SPRITES.present;
    case "sad":
    case "stress":
      return SPRITES.think;
    case "zen":
    default:
      return SPRITES.idle;
  }
}

/** Holograma de las fotos de referencia: sprites reales, no un palito SVG. */
export function CedHoloBotPuppet({ gesture }: Props) {
  const src = useMemo(() => spriteFor(gesture), [gesture]);

  useEffect(() => {
    Object.values(SPRITES).forEach((url) => {
      const img = new Image();
      img.src = url;
    });
  }, []);

  return (
    <div className="ced-holo-photo relative h-[13.5rem] w-[10.2rem] sm:h-[16rem] sm:w-[12rem] lg:h-[19rem] lg:w-[14.2rem]">
      <img
        src={src}
        alt=""
        draggable={false}
        className="ced-holo-photo-img pointer-events-none h-full w-full select-none object-contain object-bottom"
      />
    </div>
  );
}
