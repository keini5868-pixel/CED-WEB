"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
import { syncPendingGoogleProviderToken } from "@/lib/api/google";
import { createClient } from "@/lib/supabase/client";

/** Gmail/Calendar — poll frecuente. */
const CONNECTION_REFRESH_MS = 90 * 1000;
/** Clima / aire / polen — en segundo plano. */
const WEATHER_REFRESH_MS = 15 * 60 * 1000;

function capitalizeDateLabel(label: string): string {
  const trimmed = label.trim();
  if (!trimmed) return trimmed;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

export function hasRealWeatherData(lines: string[]): boolean {
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
    calendar: {
      ...prev.calendar,
      ...conn.calendar,
      title: "CALENDARIO",
      connected: prev.calendar.connected || conn.calendar.connected,
      today_events: conn.calendar.today_events ?? prev.calendar.today_events,
      week_events: conn.calendar.week_events ?? prev.calendar.week_events,
    },
    gmail: {
      ...prev.gmail,
      ...conn.gmail,
      title: "GMAIL",
      connected: prev.gmail.connected || conn.gmail.connected,
      items: conn.gmail.items ?? prev.gmail.items,
    },
  };
}

export function useHudLifeData() {
  const [data, setData] = useState<LifeDashboardSnapshot>(() => createLifeFallback());
  const [refreshingConnections, setRefreshingConnections] = useState(false);
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const bootstrappedRef = useRef(false);
  const weatherBusyRef = useRef(false);

  /** Rápido — Calendar/Gmail (~1s). */
  const refreshConnections = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshingConnections(true);
    try {
      const conn = await fetchHudConnections();
      setData((prev) => mergeConnectionSlice(prev, conn));
    } finally {
      if (showSpinner) setRefreshingConnections(false);
    }
  }, []);

  /** Lento — clima, aire, polen (no bloquea Gmail/Calendar). */
  const refreshLifeContent = useCallback(async () => {
    if (weatherBusyRef.current) return;
    weatherBusyRef.current = true;
    setLoadingWeather(true);
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
          today_events:
            snapshot.calendar.today_events?.length
              ? snapshot.calendar.today_events
              : prev.calendar.today_events,
          week_events:
            snapshot.calendar.week_events?.length
              ? snapshot.calendar.week_events
              : prev.calendar.week_events,
          error: snapshot.calendar.error ?? prev.calendar.error,
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
      /* Mantener datos previos */
    } finally {
      weatherBusyRef.current = false;
      setLoadingWeather(false);
    }
  }, []);

  const refreshConnectionsBg = useCallback(() => {
    void refreshConnections(false);
  }, [refreshConnections]);

  const refreshWeatherBg = useCallback(() => {
    void refreshLifeContent();
  }, [refreshLifeContent]);

  /** Manual ↻ — solo espera conexiones; clima en background. */
  const refresh = useCallback(async () => {
    await refreshConnections(true);
    refreshWeatherBg();
  }, [refreshConnections, refreshWeatherBg]);

  useEffect(() => {
    const supabase = createClient();
    let cancelled = false;

    const bootstrap = async () => {
      const oauth = await syncPendingGoogleProviderToken();
      if (oauth.ok && oauth.type) {
        window.dispatchEvent(
          new Event(
            oauth.type === "calendar"
              ? GOOGLE_CALENDAR_CONNECTED_EVENT
              : GOOGLE_GMAIL_CONNECTED_EVENT,
          ),
        );
      }
      if (cancelled) return;
      await refreshConnections(false);
      bootstrappedRef.current = true;
      refreshWeatherBg();
    };

    void supabase.auth.getSession().then(({ data }) => {
      if (data.session?.access_token) {
        setSessionReady(true);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (session?.access_token) {
        setSessionReady(true);
      }
      if (
        session?.access_token &&
        (event === "SIGNED_IN" ||
          event === "TOKEN_REFRESHED" ||
          event === "INITIAL_SESSION")
      ) {
        refreshConnectionsBg();
        if (bootstrappedRef.current) {
          refreshWeatherBg();
        }
      }
    });

    void bootstrap();

    const connInterval = setInterval(refreshConnectionsBg, CONNECTION_REFRESH_MS);
    const weatherInterval = setInterval(refreshWeatherBg, WEATHER_REFRESH_MS);

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        refreshConnectionsBg();
      }
    };
    const onFocus = () => {
      refreshConnectionsBg();
    };

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onFocus);

    const onGoogleConnected = () => {
      void refreshConnections(false).then(() => refreshWeatherBg());
    };
    window.addEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onGoogleConnected);
    window.addEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onGoogleConnected);

    return () => {
      cancelled = true;
      subscription.unsubscribe();
      clearInterval(connInterval);
      clearInterval(weatherInterval);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onGoogleConnected);
      window.removeEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onGoogleConnected);
    };
  }, [refreshConnections, refreshConnectionsBg, refreshWeatherBg]);

  useEffect(() => {
    if (!sessionReady) return;
    refreshConnectionsBg();
  }, [sessionReady, refreshConnectionsBg]);

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
    refreshing: refreshingConnections,
    refreshingConnections,
    loadingWeather,
    refresh,
    refreshConnections: refreshConnectionsBg,
    weatherSummary,
    calendarSummary,
    castilloStripText,
  };
}
