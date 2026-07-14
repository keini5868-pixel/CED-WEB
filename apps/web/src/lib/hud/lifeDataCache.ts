import type { LifeDashboardSnapshot } from "../api/hud";

const CACHE_KEY = "ced:hud-life-snapshot-v1";
/** Mostrar caché aunque esté vieja; el refresh en background la pone al día. */
const MAX_DISPLAY_AGE_MS = 24 * 60 * 60 * 1000;

type CachedPayload = {
  savedAt: number;
  snapshot: LifeDashboardSnapshot;
};

function isSnapshotShape(value: unknown): value is LifeDashboardSnapshot {
  if (!value || typeof value !== "object") return false;
  const snap = value as Partial<LifeDashboardSnapshot>;
  return Boolean(
    snap.weather &&
      snap.calendar &&
      snap.gmail &&
      snap.air_quality &&
      snap.pollen,
  );
}

/** True si el snapshot tiene contenido útil (no solo el fallback vacío). */
export function hasUsefulLifeCache(snapshot: LifeDashboardSnapshot): boolean {
  const weatherLine = (snapshot.weather.lines[0] ?? "").trim();
  const hasWeather =
    /\d+\s*°[CF]?/i.test(weatherLine) ||
    (weatherLine.length > 18 && !/^charlotte\s*nc?$/i.test(weatherLine));
  const hasAir = snapshot.air_quality.lines.some(
    (line) => line && !/no disponible/i.test(line),
  );
  const hasPollen = snapshot.pollen.lines.some(
    (line) => line && !/no disponible/i.test(line),
  );
  return (
    hasWeather ||
    hasAir ||
    hasPollen ||
    snapshot.gmail.connected ||
    snapshot.calendar.connected ||
    (snapshot.gmail.messages?.length ?? 0) > 0 ||
    (snapshot.calendar.events?.length ?? 0) > 0
  );
}

export function readLifeCache(): LifeDashboardSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedPayload;
    if (!parsed || typeof parsed.savedAt !== "number") return null;
    if (Date.now() - parsed.savedAt > MAX_DISPLAY_AGE_MS) return null;
    if (!isSnapshotShape(parsed.snapshot)) return null;
    if (!hasUsefulLifeCache(parsed.snapshot)) return null;
    return parsed.snapshot;
  } catch {
    return null;
  }
}

export function writeLifeCache(snapshot: LifeDashboardSnapshot): void {
  if (typeof window === "undefined") return;
  if (!hasUsefulLifeCache(snapshot)) return;
  try {
    const payload: CachedPayload = {
      savedAt: Date.now(),
      snapshot,
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}
