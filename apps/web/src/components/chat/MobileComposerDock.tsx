"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export const MOBILE_COMPOSER_DOCK_ID = "ced-mobile-composer-dock";

const LG_QUERY = "(min-width: 1024px)";

/** En móvil embebe las acciones del composer en el rail derecho. */
export function useMobileComposerDock(enabled: boolean) {
  const [target, setTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (!enabled) {
      setTarget(null);
      return;
    }

    const mq = window.matchMedia(LG_QUERY);
    const sync = () => {
      if (mq.matches) {
        setTarget(null);
        return;
      }
      setTarget(document.getElementById(MOBILE_COMPOSER_DOCK_ID));
    };

    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [enabled]);

  return target;
}

export function MobileComposerActions({
  target,
  children,
}: {
  target: HTMLElement | null;
  children: ReactNode;
}) {
  const cluster = target ? (
    <div className="flex flex-col items-center gap-1.5">{children}</div>
  ) : (
    <div className="flex shrink-0 items-center justify-end gap-1 sm:gap-1.5">{children}</div>
  );

  if (target) return createPortal(cluster, target);
  return cluster;
}
