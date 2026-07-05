import type { NavLatLng } from "@/lib/api/navigation";

const EARTH_RADIUS_M = 6_371_000;

/** Distancia para anunciar el giro (CED habla la instrucción). */
export const NAV_ANNOUNCE_DISTANCE_M = 300;
/** Distancia para marcar un step como completado. */
export const NAV_STEP_COMPLETE_M = 50;
/** Distancia para considerar llegada al destino. */
export const NAV_ARRIVAL_DISTANCE_M = 50;

/** Zoom / cámara en navegación activa (estilo Google Maps). */
export const NAV_FOLLOW_ZOOM = 19;
export const NAV_FOLLOW_TILT = 55;
export const NAV_IDLE_ZOOM = 15;
/** Desplaza el centro de cámara hacia adelante — la flecha queda en el tercio inferior. */
export const NAV_CAMERA_OFFSET_M = 110;
/** Padding para centrar la flecha entre paneles superior e inferior. */
export const NAV_MAP_PADDING = { top: 140, bottom: 260, left: 0, right: 0 };

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

/** Desplaza un punto en la dirección del rumbo (metros). */
export function offsetLatLng(
  point: NavLatLng,
  headingDeg: number,
  distanceM: number,
): NavLatLng {
  if (distanceM <= 0) return point;
  const rad = (headingDeg * Math.PI) / 180;
  const angular = distanceM / EARTH_RADIUS_M;
  const latRad = (point.lat * Math.PI) / 180;
  const dLat = angular * Math.cos(rad) * (180 / Math.PI);
  const dLng = (angular * Math.sin(rad) * (180 / Math.PI)) / Math.max(0.2, Math.cos(latRad));
  return { lat: point.lat + dLat, lng: point.lng + dLng };
}

export function navigationHeading(
  position: NavLatLng,
  path: NavLatLng[],
  gpsHeading: number | null | undefined,
  speedMps: number | null | undefined = null,
): number {
  let routeHeading: number | null = null;
  if (path.length) {
    const idx = closestPathIndex(path, position);
    const next = path[Math.min(idx + 1, path.length - 1)] ?? position;
    if (next.lat !== position.lat || next.lng !== position.lng) {
      routeHeading = bearingDegrees(position, next);
    }
  }

  if (
    speedMps != null &&
    speedMps > 2 &&
    gpsHeading != null &&
    !Number.isNaN(gpsHeading)
  ) {
    return gpsHeading;
  }
  if (routeHeading != null) return routeHeading;
  if (gpsHeading != null && !Number.isNaN(gpsHeading)) {
    return gpsHeading;
  }
  return 0;
}

export function cancelBrowserNavigationSpeech(): void {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
}

let mapSpeechSilencerInstalled = false;

/** Bloquea TTS del navegador/mapa — solo CED (Retell) habla durante navegación. */
export function installMapSpeechSilencer(): void {
  if (typeof window === "undefined" || !window.speechSynthesis || mapSpeechSilencerInstalled) {
    return;
  }
  mapSpeechSilencerInstalled = true;
  cancelBrowserNavigationSpeech();

  const synth = window.speechSynthesis;
  synth.cancel();
  synth.speak = () => {};
}

/** @deprecated Solo CED habla — no usar TTS del navegador en el mapa. */
export function speakNavigation(_text: string): void {
  cancelBrowserNavigationSpeech();
}
