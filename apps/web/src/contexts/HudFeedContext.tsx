"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type HudFeedKind = "voice" | "news" | "stat" | "report" | "image";

export interface HudFeedItem {
  id: string;
  kind: HudFeedKind;
  text: string;
  at: number;
  imageUrl?: string;
  imagePrompt?: string;
  role?: "user" | "model";
  partial?: boolean;
}

interface HudFeedContextValue {
  items: HudFeedItem[];
  voiceItems: HudFeedItem[];
  marqueeText: string;
  pushLine: (text: string, kind?: HudFeedKind) => void;
  pushVoiceLine: (
    text: string,
    role: "user" | "model",
    options?: { partial?: boolean },
  ) => void;
  pushVoiceImage: (url: string, prompt?: string) => void;
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

  const pushVoiceLine = useCallback(
    (text: string, role: "user" | "model", options?: { partial?: boolean }) => {
      const trimmed = text.replace(/\s+/g, " ").trim();
      if (!trimmed) return;
      const kind: HudFeedKind = role === "user" ? "voice" : "report";
      const partial = options?.partial ?? false;
      setVoiceItems((prev) => {
        if (role === "model" && prev.length > 0) {
          const head = prev[0];
          if (head) {
            const sameTurn =
              head.role === "model" &&
              (partial || head.partial || Date.now() - head.at < 45_000);
            if (sameTurn) {
              const merged: HudFeedItem = {
                ...head,
                text: trimmed,
                at: Date.now(),
                partial,
                role: "model",
              };
              return [merged, ...prev.slice(1)];
            }
          }
        }
        const next: HudFeedItem[] = [
          {
            id: `v-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            kind,
            text: trimmed,
            at: Date.now(),
            role,
            partial,
          },
          ...prev,
        ];
        return next.slice(0, MAX_ITEMS);
      });
    },
    [],
  );

  const pushVoiceImage = useCallback((url: string, prompt?: string) => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setVoiceItems((prev) => {
      const next: HudFeedItem[] = [
        {
          id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          kind: "image",
          text: prompt?.trim() || "Imagen generada por CED",
          imageUrl: trimmed,
          imagePrompt: prompt,
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
    () => ({ items, voiceItems, marqueeText, pushLine, pushVoiceLine, pushVoiceImage }),
    [items, voiceItems, marqueeText, pushLine, pushVoiceLine, pushVoiceImage],
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
