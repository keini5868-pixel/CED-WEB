"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export const COMPOSER_BAR_ID = "ced-composer-bar";
export const COMPOSER_ACTIONS_ID = "ced-composer-actions";

export function useComposerSplit(enabled: boolean) {
  const [bar, setBar] = useState<HTMLElement | null>(null);
  const [actions, setActions] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (!enabled) {
      setBar(null);
      setActions(null);
      return;
    }
    setBar(document.getElementById(COMPOSER_BAR_ID));
    setActions(document.getElementById(COMPOSER_ACTIONS_ID));
  }, [enabled]);

  return { bar, actions };
}

export function SplitPortal({
  target,
  children,
}: {
  target: HTMLElement | null;
  children: ReactNode;
}) {
  if (!target) return <>{children}</>;
  return createPortal(children, target);
}
