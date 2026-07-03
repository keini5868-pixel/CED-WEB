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
import { mergeTranscriptChunk } from "@/lib/voice/transcriptAccumulator";

function sameVoiceBlockPrefix(a: string, b: string): boolean {
  const na = a.trim().toLowerCase();
  const nb = b.trim().toLowerCase();
  if (!na || !nb) return false;
  if (na === nb) return true;
  const n = Math.min(na.length, nb.length, 55);
  return n >= 28 && na.slice(0, n) === nb.slice(0, n);
}

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
  uploadStatus?: "uploading" | "ready" | "error";
  fileName?: string;
  fileSize?: number;
}

export interface HudVoiceImageOptions {
  prompt?: string;
  fileName?: string;
  fileSize?: number;
  status?: "uploading" | "ready" | "error";
  role?: "user" | "model";
  id?: string;
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
  pushVoiceImage: (url: string, options?: HudVoiceImageOptions) => string;
  updateVoiceImage: (id: string, patch: Partial<HudFeedItem>) => void;
  removeVoiceImage: (id: string) => void;
  clearAgentPartial: () => void;
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
      const partial = options?.partial ?? false;
      const streamKey = options?.streamKey;

      if (!trimmed) {
        if (streamKey) {
          setVoiceItems((prev) =>
            prev.filter((item) => !(item.streamKey === streamKey && item.role === role)),
          );
        }
        return;
      }

      const kind: HudFeedKind = role === "user" ? "voice" : "report";

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
              text: mergeTranscriptChunk(existing.text, trimmed),
              at: Date.now(),
              partial,
              kind,
              role,
            };
            return [merged, ...prev.filter((_, i) => i !== idx)].slice(0, MAX_ITEMS);
          }
        }

        if (role === "user" && prev.length > 0) {
          const head = prev[0];
          if (head?.role === "user" && head.kind === "voice") {
            const sameTurn =
              partial ||
              head.partial ||
              Date.now() - head.at < 45_000;
            if (
              sameTurn &&
              (streamKey ? head.streamKey === streamKey : true) &&
              (mergeTranscriptChunk(head.text, trimmed).length >= head.text.length ||
                trimmed.startsWith(head.text.trim()))
            ) {
              const merged: HudFeedItem = {
                ...head,
                text: mergeTranscriptChunk(head.text, trimmed),
                at: Date.now(),
                partial,
                role: "user",
                streamKey: streamKey ?? head.streamKey,
              };
              return [merged, ...prev.slice(1)];
            }
          }
        }

        if (role === "model" && prev.length > 0) {
          const head = prev[0];
          if (head?.role === "model" && head.kind === "report") {
            const sameTurn =
              partial ||
              head.partial ||
              Date.now() - head.at < 45_000;
            if (
              sameTurn &&
              (streamKey ? head.streamKey === streamKey : true)
            ) {
              const merged: HudFeedItem = {
                ...head,
                text: mergeTranscriptChunk(head.text, trimmed),
                at: Date.now(),
                partial,
                role: "model",
                streamKey: streamKey ?? head.streamKey,
              };
              return [merged, ...prev.slice(1)];
            }
            if (
              !partial &&
              !head.partial &&
              sameVoiceBlockPrefix(head.text, trimmed)
            ) {
              const merged: HudFeedItem = {
                ...head,
                text: trimmed.length >= head.text.length ? trimmed : head.text,
                at: Date.now(),
                partial: false,
                role: "model",
                streamKey: head.streamKey ?? streamKey,
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

  const pushVoiceImage = useCallback((url: string, options?: HudVoiceImageOptions) => {
    const trimmed = url.trim();
    if (!trimmed) return "";
    const id = options?.id || `img-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const status = options?.status ?? "ready";
    const label =
      options?.prompt?.trim() ||
      (status === "uploading"
        ? "Subiendo imagen…"
        : status === "ready"
          ? "Imagen lista para CED"
          : "Error al subir imagen");
    setVoiceItems((prev) => {
      const without = prev.filter((item) => item.id !== id);
      const next: HudFeedItem[] = [
        {
          id,
          kind: "image",
          text: label,
          imageUrl: trimmed,
          imagePrompt: options?.prompt,
          at: Date.now(),
          role: options?.role ?? "user",
          uploadStatus: status,
          fileName: options?.fileName,
          fileSize: options?.fileSize,
        },
        ...without,
      ];
      return next.slice(0, MAX_ITEMS);
    });
    return id;
  }, []);

  const updateVoiceImage = useCallback((id: string, patch: Partial<HudFeedItem>) => {
    setVoiceItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...patch, at: Date.now() } : item)),
    );
  }, []);

  const removeVoiceImage = useCallback((id: string) => {
    setVoiceItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const clearAgentPartial = useCallback(() => {
    setVoiceItems((prev) =>
      prev.filter((item) => !(item.role === "model" && item.partial)),
    );
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
    () => ({
      items,
      voiceItems,
      marqueeText,
      pushLine,
      pushVoiceLine,
      pushVoiceImage,
      updateVoiceImage,
      removeVoiceImage,
      clearAgentPartial,
    }),
    [
      items,
      voiceItems,
      marqueeText,
      pushLine,
      pushVoiceLine,
      pushVoiceImage,
      updateVoiceImage,
      removeVoiceImage,
      clearAgentPartial,
    ],
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
