import type { NavLatLng } from "@/lib/api/navigation";

const EARTH_RADIUS_M = 6_371_000;

/** Distancia para anunciar el giro (CED habla la instrucción). */
export const NAV_ANNOUNCE_DISTANCE_M = 300;
/** Distancia para marcar un step como completado. */
export const NAV_STEP_COMPLETE_M = 50;
/** Distancia para considerar llegada al destino. */
export const NAV_ARRIVAL_DISTANCE_M = 50;

/** Zoom / cámara en navegación activa (estilo Google Maps / Waze — cercana). */
export const NAV_FOLLOW_ZOOM = 19.6;
export const NAV_FOLLOW_TILT = 68;
export const NAV_IDLE_ZOOM = 15;
/**
 * Vista de un POI específico (aproximación a flyover):
 * ROADMAP vectorial + tilt — no es Photorealistic 3D Tiles (eso requiere otro producto Google).
 */
export const DESTINATION_VIEW_ZOOM = 17.9;
export const DESTINATION_VIEW_TILT = 62;
/** Overview de varias opciones (categoría genérica). */
export const CATEGORY_OVERVIEW_MAX_ZOOM = 14.8;
/** Tras fitBounds de ruta completa, no alejar más que esto. */
export const ROUTE_PREVIEW_MIN_ZOOM = 13.5;
/** Padding del mapa en navegación — flecha del usuario centrada abajo. */
export const NAV_MAP_PADDING = { top: 48, bottom: 220, left: 28, right: 28 } as const;

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

/** Ancla el pin a la polilínea (evita flecha al lado de la ruta). */
export function snapToRoutePath(path: NavLatLng[], point: NavLatLng): NavLatLng {
  if (path.length < 1) return point;
  if (path.length === 1) return path[0]!;

  const idx = closestPathIndex(path, point);
  const prev = path[Math.max(0, idx - 1)]!;
  const curr = path[idx]!;
  const next = path[Math.min(path.length - 1, idx + 1)]!;

  const project = (a: NavLatLng, b: NavLatLng): NavLatLng => {
    const abLat = b.lat - a.lat;
    const abLng = b.lng - a.lng;
    const apLat = point.lat - a.lat;
    const apLng = point.lng - a.lng;
    const ab2 = abLat * abLat + abLng * abLng;
    if (ab2 <= 0) return a;
    const t = Math.max(0, Math.min(1, (apLat * abLat + apLng * abLng) / ab2));
    return { lat: a.lat + abLat * t, lng: a.lng + abLng * t };
  };

  const onPrev = project(prev, curr);
  const onNext = project(curr, next);
  return distanceMeters(point, onPrev) <= distanceMeters(point, onNext)
    ? onPrev
    : onNext;
}

export function offsetByMeters(
  origin: NavLatLng,
  bearingDeg: number,
  distanceM: number,
): NavLatLng {
  const angular = distanceM / EARTH_RADIUS_M;
  const bearing = (bearingDeg * Math.PI) / 180;
  const lat1 = (origin.lat * Math.PI) / 180;
  const lng1 = (origin.lng * Math.PI) / 180;

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) +
      Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
  );
  const lng2 =
    lng1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    );

  return {
    lat: (lat2 * 180) / Math.PI,
    lng: (((lng2 * 180) / Math.PI + 540) % 360) - 180,
  };
}

/** Zoom dinámico: más cercano en ciudad (estilo Waze), un poco más lejos en autopista. */
export function navigationFollowZoom(speedMps: number | null | undefined): number {
  const speed = speedMps ?? 0;
  if (speed > 22) return 18.0;
  if (speed > 12) return 18.8;
  if (speed > 4) return 19.4;
  return NAV_FOLLOW_ZOOM;
}

/** Suaviza giros bruscos de la cámara entre ticks GPS. */
export function smoothHeading(
  previous: number | null | undefined,
  next: number,
  maxDelta = 28,
): number {
  if (previous == null || Number.isNaN(previous)) return next;
  let delta = ((next - previous + 540) % 360) - 180;
  if (Math.abs(delta) > maxDelta) {
    delta = Math.sign(delta) * maxDelta;
  }
  return (previous + delta + 360) % 360;
}

/** Punto de mira adelante en la ruta — centra la cámara como Google Maps. */
export function navigationLookAheadCenter(
  position: NavLatLng,
  path: NavLatLng[],
  heading: number,
  speedMps: number | null | undefined,
): NavLatLng {
  const speed = speedMps ?? 0;
  // Look-ahead corto → cámara más “primera persona” (Waze), no panorama de toda la ruta.
  const aheadM = Math.min(70, Math.max(18, speed * 5 + 22));

  if (path.length >= 2) {
    const idx = closestPathIndex(path, position);
    let acc = 0;
    for (let i = idx; i < path.length - 1; i += 1) {
      const from = path[i]!;
      const to = path[i + 1]!;
      const seg = distanceMeters(from, to);
      if (seg <= 0) continue;
      if (acc + seg >= aheadM) {
        const ratio = (aheadM - acc) / seg;
        return {
          lat: from.lat + (to.lat - from.lat) * ratio,
          lng: from.lng + (to.lng - from.lng) * ratio,
        };
      }
      acc += seg;
    }
    return path[path.length - 1]!;
  }

  return offsetByMeters(position, heading, aheadM);
}

export function navigationHeading(
  position: NavLatLng,
  path: NavLatLng[],
  gpsHeading: number | null | undefined,
  speedMps: number | null | undefined = null,
): number {
  let routeHeading: number | null = null;
  if (path.length >= 2) {
    const snapped = snapToRoutePath(path, position);
    const idx = closestPathIndex(path, snapped);
    const lookIdx = Math.min(idx + Math.max(2, Math.floor(path.length * 0.01) + 2), path.length - 1);
    const next = path[lookIdx] ?? path[path.length - 1]!;
    if (next.lat !== snapped.lat || next.lng !== snapped.lng) {
      routeHeading = bearingDegrees(snapped, next);
    } else if (idx + 1 < path.length) {
      routeHeading = bearingDegrees(snapped, path[idx + 1]!);
    }
  }

  // Priorizar rumbo de la ruta (orientación «hacia arriba»). GPS solo a velocidad.
  if (
    speedMps != null &&
    speedMps > 3.5 &&
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
export function speakNavigation(): void {
  cancelBrowserNavigationSpeech();
}
