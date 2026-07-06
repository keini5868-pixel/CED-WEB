import type { CarouselSnapshot } from "@/components/dashboard/carousel/types";

import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";
import {
  fetchGoogleCalendarStatus,
  fetchGoogleGmailStatus,
} from "@/lib/api/google";

export type LifeDashboardSnapshot = {
  date_label: string;
  place?: string;
  updated_at: string;
  weather: { title: string; lines: string[] };
  calendar: {
    title: string;
    connected: boolean;
    events: string[];
    hint?: string;
  };
  gmail: {
    title: string;
    connected: boolean;
    unread_count: number;
    messages: string[];
    hint?: string;
  };
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
    calendar: {
      title: "CALENDARIO",
      connected: false,
      events: [],
      hint: "Conectar Calendar en CFG ⚙️",
    },
    gmail: {
      title: "GMAIL",
      connected: false,
      unread_count: 0,
      messages: [],
      hint: "Conectar Gmail en CFG ⚙️",
    },
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
  const calendarRaw = (raw.calendar ?? {}) as Record<string, unknown>;
  const gmailRaw = (raw.gmail ?? {}) as Record<string, unknown>;
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
    calendar: {
      title: "CALENDARIO",
      connected: Boolean(calendarRaw.connected),
      events: Array.isArray(calendarRaw.events)
        ? calendarRaw.events.map((e) => String(e))
        : [],
      hint:
        typeof calendarRaw.hint === "string" && calendarRaw.hint
          ? calendarRaw.hint
          : fallback.calendar.hint,
    },
    gmail: {
      title: "GMAIL",
      connected: Boolean(gmailRaw.connected),
      unread_count: Number(gmailRaw.unread_count ?? 0),
      messages: Array.isArray(gmailRaw.messages)
        ? gmailRaw.messages.map((m) => String(m))
        : [],
      hint:
        typeof gmailRaw.hint === "string" && gmailRaw.hint
          ? gmailRaw.hint
          : fallback.gmail.hint,
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

/** Fusiona estado OAuth desde endpoints rápidos de Google (calendar/gmail status). */
export async function applyGoogleConnections(
  snapshot: LifeDashboardSnapshot,
): Promise<LifeDashboardSnapshot> {
  const [cal, mail] = await Promise.all([
    fetchGoogleCalendarStatus(),
    fetchGoogleGmailStatus(),
  ]);
  if (cal?.connected) {
    snapshot.calendar.connected = true;
    snapshot.calendar.hint = "";
    if (!snapshot.calendar.events.length) {
      snapshot.calendar.events = ["Sin eventos programados para hoy."];
    }
  }
  if (mail?.connected) {
    snapshot.gmail.connected = true;
    snapshot.gmail.hint = "";
    if (!snapshot.gmail.messages.length) {
      snapshot.gmail.messages = ["Bandeja al día — sin correos sin leer."];
    }
  }
  return snapshot;
}

/** Calendar + Gmail — endpoint rápido (~1s), sin clima web. */
export async function fetchHudConnections(): Promise<
  Pick<LifeDashboardSnapshot, "calendar" | "gmail" | "updated_at">
> {
  try {
    const res = await proxyFetchAuthed("hud/connections");
    if (!res.ok) {
      const fallback = await applyGoogleConnections(createLifeFallback());
      return {
        updated_at: fallback.updated_at,
        calendar: fallback.calendar,
        gmail: fallback.gmail,
      };
    }
    const raw = (await res.json()) as Record<string, unknown>;
    const calendarRaw = (raw.calendar ?? {}) as Record<string, unknown>;
    const gmailRaw = (raw.gmail ?? {}) as Record<string, unknown>;
    return {
      updated_at:
        typeof raw.updated_at === "string"
          ? raw.updated_at
          : new Date().toISOString(),
      calendar: {
        title: "CALENDARIO",
        connected: Boolean(calendarRaw.connected),
        events: Array.isArray(calendarRaw.events)
          ? calendarRaw.events.map((e) => String(e))
          : [],
        hint:
          typeof calendarRaw.hint === "string" ? calendarRaw.hint : undefined,
      },
      gmail: {
        title: "GMAIL",
        connected: Boolean(gmailRaw.connected),
        unread_count: Number(gmailRaw.unread_count ?? 0),
        messages: Array.isArray(gmailRaw.messages)
          ? gmailRaw.messages.map((m) => String(m))
          : [],
        hint: typeof gmailRaw.hint === "string" ? gmailRaw.hint : undefined,
      },
    };
  } catch {
    const fallback = await applyGoogleConnections(createLifeFallback());
    return {
      updated_at: fallback.updated_at,
      calendar: fallback.calendar,
      gmail: fallback.gmail,
    };
  }
}

async function mergeGoogleConnectionStatus(
  snapshot: LifeDashboardSnapshot,
): Promise<LifeDashboardSnapshot> {
  return applyGoogleConnections(snapshot);
}

/** Dashboard LIFE — nunca devuelve null; fallback local si la API falla. */
export async function fetchHudLife(): Promise<LifeDashboardSnapshot> {
  try {
    const res = await proxyFetchAuthed("hud/life");
    if (!res.ok) {
      return mergeGoogleConnectionStatus(createLifeFallback());
    }
    const raw = (await res.json()) as Record<string, unknown>;
    return mergeGoogleConnectionStatus(normalizeLifeSnapshot(raw));
  } catch {
    return mergeGoogleConnectionStatus(createLifeFallback());
  }
}

/** LIFE con timeout — solo para llamadas opcionales; no usar para OAuth status. */
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
