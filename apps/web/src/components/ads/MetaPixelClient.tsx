"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import {
  consumeExpectedRegistration,
  metaPixelId,
  trackPageView,
} from "@/lib/ads/meta-pixel";

/** PageView en navegación SPA y registro Google al volver del OAuth. */
export function MetaPixelClient() {
  const pathname = usePathname();
  const id = metaPixelId();
  const firstPaint = useRef(true);

  useEffect(() => {
    if (!id) return;
    if (firstPaint.current) {
      firstPaint.current = false;
      consumeExpectedRegistration();
      return;
    }
    trackPageView();
    consumeExpectedRegistration();
  }, [id, pathname]);

  return null;
}
