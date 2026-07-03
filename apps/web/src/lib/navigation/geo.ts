import type { NavLatLng } from "@/lib/api/navigation";

const EARTH_RADIUS_M = 6_371_000;

export function distanceMeters(a: NavLatLng, b: NavLatLng): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function formatDistanceMeters(m: number): string {
  if (m < 1000) return `${Math.round(m / 10) * 10} metros`;
  return `${(m / 1000).toFixed(1)} kilómetros`;
}

export function bearingDegrees(
  from: NavLatLng,
  to: NavLatLng,
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const toDeg = (rad: number) => ((rad * 180) / Math.PI + 360) % 360;
  const lat1 = toRad(from.lat);
  const lat2 = toRad(to.lat);
  const dLng = toRad(to.lng - from.lng);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) -
    Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return toDeg(Math.atan2(y, x));
}

export function closestPathIndex(path: NavLatLng[], point: NavLatLng): number {
  if (!path.length) return 0;
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < path.length; i += 1) {
    const node = path[i];
    if (!node) continue;
    const d = distanceMeters(point, node);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  return bestIdx;
}

export function cancelBrowserNavigationSpeech(): void {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
}

/** @deprecated Solo CED habla — no usar TTS del navegador en el mapa. */
export function speakNavigation(_text: string): void {
  cancelBrowserNavigationSpeech();
}
