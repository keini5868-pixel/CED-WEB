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
  /** Solo diálogo voz usuario/CED — no incluye Intel/DRONES. */
  voiceItems: HudFeedItem[];
  marqueeText: string;
  pushLine: (text: string, kind?: HudFeedKind) => void;
  pushVoiceLine: (text: string, role: "user" | "model") => void;
}

const HudFeedContext = createContext<HudFeedContextValue | null>(null);

const MAX_ITEMS = 48;

export function HudFeedProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<HudFeedItem[]>([]);
  const [voiceItems, setVoiceItems] = useState<HudFeedItem[]>([]);

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

  const pushVoiceLine = useCallback((text: string, role: "user" | "model") => {
    const trimmed = text.replace(/\s+/g, " ").trim();
    if (!trimmed) return;
    const kind: HudFeedKind = role === "user" ? "voice" : "report";
    setVoiceItems((prev) => {
      const next: HudFeedItem[] = [
        {
          id: `v-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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
    () => ({ items, voiceItems, marqueeText, pushLine, pushVoiceLine }),
    [items, voiceItems, marqueeText, pushLine, pushVoiceLine],
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
