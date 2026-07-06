"use client";

import { useCallback, useEffect, useState } from "react";

import {
  GOOGLE_CALENDAR_CONNECTED_EVENT,
  GOOGLE_GMAIL_CONNECTED_EVENT,
} from "@/components/voice/ConnectGoogleServices";
import {
  createLifeFallback,
  fetchHudConnections,
  fetchHudLife,
  type LifeDashboardSnapshot,
} from "@/lib/api/hud";

function capitalizeDateLabel(label: string): string {
  const trimmed = label.trim();
  if (!trimmed) return trimmed;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

function hasRealWeatherData(lines: string[]): boolean {
  const line = (lines[0] ?? "").trim();
  if (!line) return false;
  if (/\d+\s*°[CF]?/i.test(line)) return true;
  return line.length > 18 && !/^charlotte\s*nc?$/i.test(line);
}

function formatPlace(place?: string): string {
  const raw = (place ?? "Charlotte NC").trim();
  return raw.includes(",") ? raw : raw.replace(/\s+NC$/i, ", NC");
}

function mergeConnectionSlice(
  prev: LifeDashboardSnapshot,
  conn: Pick<LifeDashboardSnapshot, "calendar" | "gmail" | "updated_at">,
): LifeDashboardSnapshot {
  return {
    ...prev,
    updated_at: conn.updated_at || prev.updated_at,
    calendar: { ...prev.calendar, ...conn.calendar, title: "CALENDARIO" },
    gmail: { ...prev.gmail, ...conn.gmail, title: "GMAIL" },
  };
}

export function useHudLifeData() {
  const [data, setData] = useState<LifeDashboardSnapshot>(() => createLifeFallback());
  const [refreshing, setRefreshing] = useState(false);

  /** Rápido — Calendar/Gmail OAuth (~1s). Siempre primero. */
  const refreshConnections = useCallback(async () => {
    const conn = await fetchHudConnections();
    setData((prev) => mergeConnectionSlice(prev, conn));
  }, []);

  /** Lento — clima, aire, polen. No resetea conexiones si falla. */
  const refreshLifeContent = useCallback(async () => {
    try {
      const snapshot = await fetchHudLife();
      setData((prev) => ({
        ...snapshot,
        calendar: {
          ...snapshot.calendar,
          connected: prev.calendar.connected || snapshot.calendar.connected,
          events: snapshot.calendar.connected
            ? snapshot.calendar.events
            : prev.calendar.events,
        },
        gmail: {
          ...snapshot.gmail,
          connected: prev.gmail.connected || snapshot.gmail.connected,
          messages: snapshot.gmail.connected
            ? snapshot.gmail.messages
            : prev.gmail.messages,
          unread_count: snapshot.gmail.connected
            ? snapshot.gmail.unread_count
            : prev.gmail.unread_count,
        },
      }));
    } catch {
      /* Mantener calendar/gmail ya cargados por refreshConnections */
    }
  }, []);

  const refresh = useCallback(
    async (showSpinner = false) => {
      if (showSpinner) setRefreshing(true);
      try {
        await refreshConnections();
        await refreshLifeContent();
      } finally {
        if (showSpinner) setRefreshing(false);
      }
    },
    [refreshConnections, refreshLifeContent],
  );

  useEffect(() => {
    void refreshConnections();
    void refreshLifeContent();
    const id = setInterval(() => {
      void refreshConnections();
      void refreshLifeContent();
    }, REFRESH_MS);
    const onCal = () => void refreshConnections();
    const onMail = () => void refreshConnections();
    window.addEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onCal);
    window.addEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onMail);
    return () => {
      clearInterval(id);
      window.removeEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onCal);
      window.removeEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onMail);
    };
  }, [refreshConnections, refreshLifeContent]);

  const weatherSummary = () => {
    const line = data.weather.lines[0] ?? "Charlotte NC";
    const tempMatch = line.match(/\d+\s*°?C/i);
    if (!tempMatch) {
      return { temp: line.split(/[,.]/)[0]?.trim() || "Charlotte NC", condition: "", line };
    }
    const temp = tempMatch[0].replace(/\s/g, "");
    const condition = line.replace(tempMatch[0], "").replace(/^[,.\s]+/, "").trim();
    return { temp, condition: condition || "Consultando", line };
  };

  const calendarSummary = () => {
    if (!data.calendar.connected) return null;
    if (!data.calendar.events.length) return "Sin eventos hoy";
    const first = data.calendar.events[0] ?? "";
    if (first.toLowerCase().includes("sin eventos")) return "Sin eventos hoy";
    return first.length > 36 ? `${first.slice(0, 36)}…` : first;
  };

  const castilloStripText = () => {
    const place = formatPlace(data.place);
    const dateLabel = capitalizeDateLabel(data.date_label);

    if (!hasRealWeatherData(data.weather.lines)) {
      return `📅 ${dateLabel} · ${place}`;
    }

    const { temp, condition, line } = weatherSummary();
    const weatherPart = condition
      ? `${temp} · ${condition} · ${place}`
      : line.includes("°")
        ? `${line} · ${place}`
        : `${temp} · ${place}`;

    const cal = calendarSummary();
    const segments = [`🌤️ ${weatherPart}`, `📅 ${dateLabel}`];
    if (cal) segments.push(cal);
    return segments.join("  |  ");
  };

  return {
    data,
    refreshing,
    refresh: () => refresh(true),
    refreshConnections,
    weatherSummary,
    calendarSummary,
    castilloStripText,
  };
}
