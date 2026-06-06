"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type HudFeedKind = "voice" | "news" | "stat" | "report";

export interface HudFeedItem {
  id: string;
  kind: HudFeedKind;
  text: string;
  at: number;
}

interface HudFeedContextValue {
  items: HudFeedItem[];
  marqueeText: string;
  pushLine: (text: string, kind?: HudFeedKind) => void;
}

const HudFeedContext = createContext<HudFeedContextValue | null>(null);

const MAX_ITEMS = 48;

export function HudFeedProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<HudFeedItem[]>([]);

  const pushLine = useCallback((text: string, kind: HudFeedKind = "voice") => {
    const trimmed = text.replace(/\s+/g, " ").trim();
    if (!trimmed) return;
    setItems((prev) => {
      const next: HudFeedItem[] = [
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          kind,
          text: trimmed,
          at: Date.now(),
        },
        ...prev,
      ];
      return next.slice(0, MAX_ITEMS);
    });
  }, []);

  const marqueeText = useMemo(() => {
    if (items.length === 0) {
      return "Sincronizando canal de inteligencia CED…";
    }
    return items
      .slice(0, 20)
      .map((i) => i.text)
      .join("  ·  ");
  }, [items]);

  const value = useMemo(
    () => ({ items, marqueeText, pushLine }),
    [items, marqueeText, pushLine],
  );

  return (
    <HudFeedContext.Provider value={value}>{children}</HudFeedContext.Provider>
  );
}

export function useHudFeed() {
  const ctx = useContext(HudFeedContext);
  if (!ctx) {
    throw new Error("useHudFeed debe usarse dentro de HudFeedProvider");
  }
  return ctx;
}
