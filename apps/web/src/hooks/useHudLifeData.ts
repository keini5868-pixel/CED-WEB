"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createLifeFallback,
  fetchHudLife,
  type LifeDashboardSnapshot,
} from "@/lib/api/hud";

const REFRESH_MS = 30 * 60 * 1000;

export function useHudLifeData() {
  const [data, setData] = useState<LifeDashboardSnapshot>(() => createLifeFallback());
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await fetchHudLife());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const weatherSummary = () => {
    const line = data.weather.lines[0] ?? "Buscando clima…";
    const tempMatch = line.match(/\d+\s*°?C/i);
    const temp = tempMatch ? tempMatch[0].replace(/\s/g, "") : line.split(/[,.]/)[0]?.trim() ?? "—";
    const condition = line.replace(tempMatch?.[0] ?? "", "").replace(/^[,.\s]+/, "").trim() || "Consultando";
    return { temp, condition, line };
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
    return `🌤️ ${temp} ${condition}  │  📅 ${calendarSummary()}`;
  };

  return { data, refreshing, refresh, weatherSummary, calendarSummary, castilloStripText };
}
