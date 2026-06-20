"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { sanitizeHudTranscript } from "@/lib/voice/hud-transcript-filter";

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
  streamKey?: string;
}

export interface HudVoiceLineOptions {
  partial?: boolean;
  streamKey?: string;
}

interface HudFeedContextValue {
  items: HudFeedItem[];
  voiceItems: HudFeedItem[];
  marqueeText: string;
  pushLine: (text: string, kind?: HudFeedKind) => void;
  pushVoiceLine: (
    text: string,
    role: "user" | "model",
    options?: HudVoiceLineOptions,
  ) => void;
  pushVoiceImage: (url: string, prompt?: string) => void;
}

const HudFeedContext = createContext<HudFeedContextValue | null>(null);

const MAX_ITEMS = 48;

export function HudFeedProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<HudFeedItem[]>([]);
  const [voiceItems, setVoiceItems] = useState<HudFeedItem[]>([]);

  const pushLine = useCallback((text: string, kind: HudFeedKind = "voice") => {
    const trimmed = sanitizeHudTranscript(text);
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
    (text: string, role: "user" | "model", options?: HudVoiceLineOptions) => {
      const trimmed = sanitizeHudTranscript(text);
      if (!trimmed) return;
      const kind: HudFeedKind = role === "user" ? "voice" : "report";
      const partial = options?.partial ?? false;
      const streamKey = options?.streamKey;

      setVoiceItems((prev) => {
        if (streamKey) {
          const idx = prev.findIndex(
            (item) => item.streamKey === streamKey && item.role === role,
          );
          if (idx >= 0) {
            const existing = prev[idx];
            if (!existing) return prev;
            const merged: HudFeedItem = {
              ...existing,
              text: trimmed,
              at: Date.now(),
              partial,
              kind,
              role,
            };
            return [merged, ...prev.filter((_, i) => i !== idx)].slice(0, MAX_ITEMS);
          }
        }

        if (role === "model" && prev.length > 0) {
          const head = prev[0];
          if (head?.role === "model") {
            const sameTurn =
              partial ||
              head.partial ||
              Date.now() - head.at < 45_000;
            if (sameTurn && (streamKey ? head.streamKey === streamKey : true)) {
              const merged: HudFeedItem = {
                ...head,
                text: trimmed,
                at: Date.now(),
                partial,
                role: "model",
                streamKey: streamKey ?? head.streamKey,
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
            streamKey,
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
