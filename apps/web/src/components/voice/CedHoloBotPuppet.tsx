"use client";

import { useEffect, useMemo, useState } from "react";

import type { PresenterGesture } from "@/lib/voice/presenterGestures";
import { spriteUrl } from "@/lib/voice/presenterSprites";

type Props = {
  gesture: PresenterGesture;
};

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

/** Holograma: una foto por gesto emocional, según presenterSprites. */
export function CedHoloBotPuppet({ gesture }: Props) {
  const raw = useMemo(() => spriteUrl(gesture), [gesture]);
  const [src, setSrc] = useState(raw);

  useEffect(() => {
    void punchBlack(spriteUrl("idle"));
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
