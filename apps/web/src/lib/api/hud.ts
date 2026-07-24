import type { CarouselSnapshot } from "@/components/dashboard/carousel/types";

import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

export type LifeDashboardSnapshot = {
  date_label: string;
  place?: string;
  updated_at: string;
  weather: { title: string; lines: string[] };
  air_quality: { title: string; lines: string[] };
  pollen: { title: string; lines: string[] };
};

async function authHeaders(): Promise<HeadersInit | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) return null;
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

function mapSnapshot(raw: Record<string, unknown>): CarouselSnapshot {
  const cards = Array.isArray(raw.cards) ? raw.cards : [];
  return {
    updatedAt:
      (typeof raw.updated_at === "string" && raw.updated_at) ||
      (typeof raw.updatedAt === "string" && raw.updatedAt) ||
      new Date().toISOString(),
    cards: cards.map((c) => {
      const card = c as Record<string, unknown>;
      return {
        id: String(card.id ?? ""),
        kind: card.kind as CarouselSnapshot["cards"][number]["kind"],
        title: String(card.title ?? ""),
        accent: card.accent as CarouselSnapshot["cards"][number]["accent"],
        lines: Array.isArray(card.lines)
          ? card.lines.map((line) => String(line))
          : [],
        footer: card.footer ? String(card.footer) : undefined,
        badge: card.badge ? String(card.badge) : undefined,
        emphasis: Boolean(card.emphasis),
      };
    }),
    prospectionMode: Boolean(raw.prospection_mode ?? raw.prospectionMode),
  };
}

/** Snapshot del carrusel HUD — null si no hay sesión o la API falla. */
export async function fetchHudCarousel(): Promise<CarouselSnapshot | null> {
  const headers = await authHeaders();
  if (!headers) return null;

  try {
    const res = await fetch(`${apiUrl()}/v1/hud/carousel`, { headers });
    if (!res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;
    const snapshot = mapSnapshot(raw);
    return snapshot.cards.length ? snapshot : null;
  } catch {
    return null;
  }
}

/** Fallback local — siempre muestra algo útil aunque falle la API. */
export function createLifeFallback(): LifeDashboardSnapshot {
  const date_label = new Date().toLocaleDateString("es", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return {
    date_label,
    place: "Charlotte NC",
    updated_at: new Date().toISOString(),
    weather: { title: "CLIMA", lines: ["Charlotte NC"] },
    air_quality: { title: "CALIDAD DEL AIRE", lines: ["No disponible."] },
    pollen: { title: "POLEN", lines: ["No disponible."] },
  };
}

function normalizeLifeSnapshot(raw: Record<string, unknown>): LifeDashboardSnapshot {
  const fallback = createLifeFallback();
  const asLines = (value: unknown, fb: string[]): string[] => {
    if (!value || typeof value !== "object") return fb;
    const lines = (value as { lines?: unknown }).lines;
    return Array.isArray(lines) && lines.length
      ? lines.map((line) => String(line))
      : fb;
  };
  return {
    date_label:
      typeof raw.date_label === "string" && raw.date_label.trim()
        ? raw.date_label
        : fallback.date_label,
    place: typeof raw.place === "string" ? raw.place : fallback.place,
    updated_at:
      typeof raw.updated_at === "string" ? raw.updated_at : fallback.updated_at,
    weather: {
      title: "CLIMA",
      lines: asLines(raw.weather, fallback.weather.lines),
    },
    air_quality: {
      title: "CALIDAD DEL AIRE",
      lines: asLines(raw.air_quality, fallback.air_quality.lines),
    },
    pollen: {
      title: "POLEN",
      lines: asLines(raw.pollen, fallback.pollen.lines),
    },
  };
}

export type HudFetchOptions = {
  /** Relativo al chat — widgets deben ir en "low". */
  priority?: "high" | "low" | "auto";
};

function withHudPriority(
  priority?: "high" | "low" | "auto",
): RequestInit | undefined {
  if (!priority) return undefined;
  return { priority } as RequestInit;
}

/** Dashboard LIFE — nunca devuelve null; fallback local si la API falla. */
export async function fetchHudLife(
  options?: HudFetchOptions,
): Promise<LifeDashboardSnapshot> {
  try {
    const res = await proxyFetchAuthed(
      "hud/life",
      withHudPriority(options?.priority),
    );
    if (!res.ok) {
      return createLifeFallback();
    }
    const raw = (await res.json()) as Record<string, unknown>;
    return normalizeLifeSnapshot(raw);
  } catch {
    return createLifeFallback();
  }
}

/** LIFE con timeout — solo para llamadas opcionales. */
export async function fetchHudLifeWithTimeout(
  timeoutMs = 5000,
): Promise<LifeDashboardSnapshot> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      fetchHudLife(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("timeout")), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
