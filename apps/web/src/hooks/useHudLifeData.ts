"use client";

import { useCallback, useEffect, useState } from "react";

import {
  GOOGLE_CALENDAR_CONNECTED_EVENT,
  GOOGLE_GMAIL_CONNECTED_EVENT,
} from "@/components/voice/ConnectGoogleServices";
import {
  createLifeFallback,
  fetchHudLife,
  fetchHudLifeWithTimeout,
  type LifeDashboardSnapshot,
} from "@/lib/api/hud";

const REFRESH_MS = 30 * 60 * 1000;
const STRIP_TIMEOUT_MS = 5000;

export function useHudLifeData() {
  const [data, setData] = useState<LifeDashboardSnapshot>(() => createLifeFallback());
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const snapshot = showSpinner
        ? await fetchHudLife()
        : await fetchHudLifeWithTimeout(STRIP_TIMEOUT_MS);
      setData(snapshot);
    } catch {
      setData(createLifeFallback());
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh(false);
    const id = setInterval(() => void refresh(false), REFRESH_MS);
    const onOAuth = () => void refresh(false);
    window.addEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onOAuth);
    window.addEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onOAuth);
    return () => {
      clearInterval(id);
      window.removeEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onOAuth);
      window.removeEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onOAuth);
    };
  }, [refresh]);

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
    if (!data.calendar.connected) return "Sin conectar";
    if (!data.calendar.events.length) return "Sin eventos";
    const first = data.calendar.events[0] ?? "";
    if (first.toLowerCase().includes("sin eventos")) return "Sin eventos";
    return first.length > 28 ? `${first.slice(0, 28)}…` : first;
  };

  const castilloStripText = () => {
    const { temp, condition } = weatherSummary();
    const weather = condition ? `${temp} ${condition}` : temp;
    return `🌤️ ${weather}  │  📅 ${calendarSummary()}`;
  };

  return {
    data,
    refreshing,
    refresh: () => refresh(true),
    weatherSummary,
    calendarSummary,
    castilloStripText,
  };
}
