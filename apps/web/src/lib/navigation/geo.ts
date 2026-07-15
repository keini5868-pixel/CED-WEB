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

function projectOnSegment(a: NavLatLng, b: NavLatLng, point: NavLatLng): NavLatLng {
  const abLat = b.lat - a.lat;
  const abLng = b.lng - a.lng;
  const apLat = point.lat - a.lat;
  const apLng = point.lng - a.lng;
  const ab2 = abLat * abLat + abLng * abLng;
  if (ab2 <= 0) return a;
  const t = Math.max(0, Math.min(1, (apLat * abLat + apLng * abLng) / ab2));
  return { lat: a.lat + abLat * t, lng: a.lng + abLng * t };
}

/** Ancla el pin a la polilínea (evita flecha al lado de la ruta). */
export function snapToRoutePath(path: NavLatLng[], point: NavLatLng): NavLatLng {
  if (path.length < 1) return point;
  if (path.length === 1) return path[0]!;
  return trackRouteProgress(path, point, null).snapped;
}

/** Dentro de este radio el usuario cuenta como «en ruta»: la geometría manda el rumbo. */
export const NAV_ON_ROUTE_MAX_M = 35;

export type RouteProgress = {
  /** Índice del vértice de ruta más cercano (monotónico si se pasa lastIdx). */
  idx: number;
  /** Posición proyectada sobre la polilínea. */
  snapped: NavLatLng;
  /** Distancia del GPS a la ruta (metros). */
  offRouteM: number;
};

/**
 * Progreso sobre la ruta con ventana alrededor del último índice conocido.
 * Evita que el ruido del GPS haga saltar el anclaje a segmentos lejanos
 * (vías paralelas, tréboles, tramos que se cruzan) o retroceder en la ruta.
 */
export function trackRouteProgress(
  path: NavLatLng[],
  point: NavLatLng,
  lastIdx: number | null | undefined,
): RouteProgress {
  if (path.length === 0) return { idx: 0, snapped: point, offRouteM: 0 };
  if (path.length === 1) {
    return { idx: 0, snapped: path[0]!, offRouteM: distanceMeters(point, path[0]!) };
  }

  let idx: number;
  if (lastIdx == null || lastIdx < 0 || lastIdx >= path.length) {
    idx = closestPathIndex(path, point);
  } else {
    const start = Math.max(0, lastIdx - 8);
    const end = Math.min(path.length - 1, lastIdx + 80);
    let bestIdx = lastIdx;
    let bestDist = Infinity;
    for (let i = start; i <= end; i += 1) {
      const d = distanceMeters(point, path[i]!);
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }
    // GPS muy lejos de la ventana (recálculo, túnel): re-búsqueda global.
    idx = bestDist > 120 ? closestPathIndex(path, point) : bestIdx;
  }

  const prev = path[Math.max(0, idx - 1)]!;
  const curr = path[idx]!;
  const next = path[Math.min(path.length - 1, idx + 1)]!;
  const onPrev = projectOnSegment(prev, curr, point);
  const onNext = projectOnSegment(curr, next, point);
  const dPrev = distanceMeters(point, onPrev);
  const dNext = distanceMeters(point, onNext);
  return dPrev <= dNext
    ? { idx, snapped: onPrev, offRouteM: dPrev }
    : { idx, snapped: onNext, offRouteM: dNext };
}

/** Punto a `aheadM` metros siguiendo la polilínea desde `fromPoint` (vértice fromIdx). */
export function pointAlongPath(
  path: NavLatLng[],
  fromIdx: number,
  fromPoint: NavLatLng,
  aheadM: number,
): NavLatLng {
  let acc = 0;
  let cursor = fromPoint;
  for (let i = Math.max(0, fromIdx); i < path.length - 1; i += 1) {
    const to = path[i + 1]!;
    const seg = distanceMeters(cursor, to);
    if (seg <= 0) {
      cursor = to;
      continue;
    }
    if (acc + seg >= aheadM) {
      const ratio = (aheadM - acc) / seg;
      return {
        lat: cursor.lat + (to.lat - cursor.lat) * ratio,
        lng: cursor.lng + (to.lng - cursor.lng) * ratio,
      };
    }
    acc += seg;
    cursor = to;
  }
  return path[path.length - 1] ?? fromPoint;
}

/** Rumbo de la ruta en el punto snapped — look-ahead por DISTANCIA (no % del path). */
export function routeHeadingAt(
  path: NavLatLng[],
  idx: number,
  snapped: NavLatLng,
  aheadM = 30,
): number | null {
  if (path.length < 2) return null;
  const target = pointAlongPath(path, idx, snapped, aheadM);
  if (distanceMeters(snapped, target) >= 2) {
    return bearingDegrees(snapped, target);
  }
  // Fin de ruta: usa el último segmento no degenerado.
  for (let i = path.length - 1; i > 0; i -= 1) {
    const a = path[i - 1]!;
    const b = path[i]!;
    if (distanceMeters(a, b) >= 1) return bearingDegrees(a, b);
  }
  return null;
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

/** Suaviza cambios de zoom por velocidad — sin saltos visibles entre escalones. */
export function smoothZoom(
  previous: number | null | undefined,
  next: number,
  maxDelta = 0.25,
): number {
  if (previous == null || Number.isNaN(previous)) return next;
  const delta = next - previous;
  if (Math.abs(delta) <= maxDelta) return next;
  return previous + Math.sign(delta) * maxDelta;
}

/** Punto de mira adelante en la ruta — centra la cámara como Google Maps. */
export function navigationLookAheadCenter(
  position: NavLatLng,
  path: NavLatLng[],
  heading: number,
  speedMps: number | null | undefined,
  fromIdx: number | null = null,
): NavLatLng {
  const speed = speedMps ?? 0;
  // Look-ahead corto → cámara más “primera persona” (Waze), no panorama de toda la ruta.
  const aheadM = Math.min(70, Math.max(18, speed * 5 + 22));

  if (path.length >= 2) {
    const idx = fromIdx ?? closestPathIndex(path, position);
    return pointAlongPath(path, idx, position, aheadM);
  }

  return offsetByMeters(position, heading, aheadM);
}

/**
 * Rumbo de navegación estable:
 * - EN RUTA (≤ NAV_ON_ROUTE_MAX_M): manda la geometría de la ruta con look-ahead
 *   por distancia — una sola fuente, sin alternar con el GPS crudo entre ticks.
 * - Fuera de ruta: GPS si es válido y hay velocidad; si no, la ruta como respaldo.
 */
export function navigationHeading(
  position: NavLatLng,
  path: NavLatLng[],
  gpsHeading: number | null | undefined,
  speedMps: number | null | undefined = null,
  lastIdx: number | null = null,
): number {
  const gpsValid =
    gpsHeading != null && !Number.isNaN(gpsHeading) && (speedMps ?? 0) > 3.5;

  if (path.length >= 2) {
    const progress = trackRouteProgress(path, position, lastIdx);
    const routeHeading = routeHeadingAt(path, progress.idx, progress.snapped);
    if (routeHeading != null && progress.offRouteM <= NAV_ON_ROUTE_MAX_M) {
      return routeHeading;
    }
    if (gpsValid) return gpsHeading;
    if (routeHeading != null) return routeHeading;
  }

  if (gpsValid) return gpsHeading;
  if (gpsHeading != null && !Number.isNaN(gpsHeading)) return gpsHeading;
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
