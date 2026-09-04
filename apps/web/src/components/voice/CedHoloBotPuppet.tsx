"use client";

import { useEffect, useMemo, useState } from "react";

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

const punchedCache = new Map<string, string>();

function punchBlack(src: string): Promise<string> {
  const hit = punchedCache.get(src);
  if (hit) return Promise.resolve(hit);
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth || 1;
      canvas.height = img.naturalHeight || 1;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        resolve(src);
        return;
      }
      ctx.drawImage(img, 0, 0);
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const px = data.data;
      for (let i = 0; i < px.length; i += 4) {
        const r = px[i] ?? 0;
        const g = px[i + 1] ?? 0;
        const b = px[i + 2] ?? 0;
        const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        const cyan = b > 42 && b + 10 >= g && b > r + 6;
        const gray = Math.abs(r - g) < 14 && Math.abs(g - b) < 14;
        if ((!cyan && lum < 44) || (!cyan && gray && lum < 78)) {
          px[i + 3] = 0;
        }
      }
      ctx.putImageData(data, 0, 0);
      const url = canvas.toDataURL("image/png");
      punchedCache.set(src, url);
      resolve(url);
    };
    img.onerror = () => resolve(src);
    img.src = src;
  });
}

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
  const raw = useMemo(() => spriteFor(gesture), [gesture]);
  const [src, setSrc] = useState(raw);

  useEffect(() => {
    Object.values(SPRITES).forEach((url) => {
      void punchBlack(url);
    });
  }, []);

  useEffect(() => {
    let live = true;
    void punchBlack(raw).then((url) => {
      if (live) setSrc(url);
    });
    return () => {
      live = false;
    };
  }, [raw]);

  return (
    <div className="ced-holo-photo relative h-[11.5rem] w-[8.6rem] bg-transparent sm:h-[13.5rem] sm:w-[10.2rem] lg:h-[16rem] lg:w-[12rem]">
      <img
        src={src}
        alt=""
        draggable={false}
        className="ced-holo-photo-img pointer-events-none h-full w-full select-none bg-transparent object-contain object-bottom"
      />
    </div>
  );
}
