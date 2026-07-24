"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

import type { LifeDashboardSnapshot } from "@/lib/api/hud";
import {
  ensureLifeStoreStarted,
  getLifeStoreServerSnapshot,
  getLifeStoreSnapshot,
  refreshLifeStoreConnections,
  refreshLifeStoreManual,
  subscribeLifeStore,
} from "@/lib/hud/lifeDataStore";

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

function weatherSummaryFrom(data: LifeDashboardSnapshot) {
  const line = data.weather.lines[0] ?? "Charlotte NC";
  const tempMatch = line.match(/\d+\s*°?C/i);
  if (!tempMatch) {
    return {
      temp: line.split(/[,.]/)[0]?.trim() || "Charlotte NC",
      condition: "",
      line,
    };
  }
  const temp = tempMatch[0].replace(/\s/g, "");
  const condition = line
    .replace(tempMatch[0], "")
    .replace(/^[,.\s]+/, "")
    .trim();
  return { temp, condition: condition || "Consultando", line };
}

/**
 * Datos LIFE del HUD. Caché inmediato + refresh silencioso en background.
 * No bloquea el chat de texto — store singleton (un fetch, N suscriptores).
 */
export function useHudLifeData() {
  const { data, refreshingConnections, loadingWeather } = useSyncExternalStore(
    subscribeLifeStore,
    getLifeStoreSnapshot,
    getLifeStoreServerSnapshot,
  );

  useEffect(() => {
    ensureLifeStoreStarted();
  }, []);

  const refresh = useCallback(async () => {
    await refreshLifeStoreManual();
  }, []);

  const refreshConnectionsBg = useCallback(() => {
    refreshLifeStoreConnections();
  }, []);

  const weatherSummary = useCallback(() => weatherSummaryFrom(data), [data]);

  const castilloStripText = useCallback(() => {
    const place = formatPlace(data.place);
    const dateLabel = capitalizeDateLabel(data.date_label);

    if (!hasRealWeatherData(data.weather.lines)) {
      return `📅 ${dateLabel} · ${place}`;
    }

    const { temp, condition, line } = weatherSummaryFrom(data);
    const weatherPart = condition
      ? `${temp} · ${condition} · ${place}`
      : line.includes("°")
        ? `${line} · ${place}`
        : `${temp} · ${place}`;

    return [`🌤️ ${weatherPart}`, `📅 ${dateLabel}`].join("  |  ");
  }, [data]);

  return {
    data,
    refreshing: refreshingConnections,
    refreshingConnections,
    loadingWeather,
    refresh,
    refreshConnections: refreshConnectionsBg,
    weatherSummary,
    castilloStripText,
  };
}
