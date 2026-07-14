import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

import {
  hasUsefulLifeCache,
  readLifeCache,
  writeLifeCache,
} from "./lifeDataCache";

type Snap = Parameters<typeof writeLifeCache>[0];

function emptySnap(): Snap {
  return {
    date_label: "lunes",
    place: "Charlotte NC",
    updated_at: new Date().toISOString(),
    weather: { title: "CLIMA", lines: ["Charlotte NC"] },
    calendar: {
      title: "CALENDARIO",
      connected: false,
      events: [],
      hint: "x",
    },
    gmail: {
      title: "GMAIL",
      connected: false,
      unread_count: 0,
      messages: [],
      hint: "x",
    },
    air_quality: { title: "CALIDAD DEL AIRE", lines: ["No disponible."] },
    pollen: { title: "POLEN", lines: ["No disponible."] },
  };
}

function richSnap(): Snap {
  const base = emptySnap();
  return {
    ...base,
    weather: { title: "CLIMA", lines: ["22°C · Soleado · Charlotte, NC"] },
    air_quality: { title: "CALIDAD DEL AIRE", lines: ["Buena · AQI 42"] },
    gmail: {
      ...base.gmail,
      connected: true,
      messages: ["De: Ana — Reunión"],
      unread_count: 1,
    },
  };
}

describe("lifeDataCache", () => {
  const memory = new Map<string, string>();

  beforeEach(() => {
    memory.clear();
    const storage = {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => {
        memory.set(key, value);
      },
      removeItem: (key: string) => {
        memory.delete(key);
      },
    };
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("window", { localStorage: storage });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("detects useful vs empty fallback", () => {
    expect(hasUsefulLifeCache(emptySnap())).toBe(false);
    expect(hasUsefulLifeCache(richSnap())).toBe(true);
  });

  it("round-trips useful snapshot for instant paint", () => {
    writeLifeCache(richSnap());
    const cached = readLifeCache();
    expect(cached?.weather.lines[0]).toContain("22°C");
    expect(cached?.gmail.connected).toBe(true);
  });

  it("ignores empty fallback writes", () => {
    writeLifeCache(emptySnap());
    expect(readLifeCache()).toBeNull();
  });
});
