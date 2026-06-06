import type { CarouselSnapshot } from "@/components/dashboard/carousel/types";

import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

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
