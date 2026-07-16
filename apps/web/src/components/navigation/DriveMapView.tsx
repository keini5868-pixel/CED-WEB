"use client";

import { useEffect, useRef, useState } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import { loadGoogleMaps } from "@/lib/maps/loadGoogleMaps";
import {
  CED_MAP_ID,
  createDestinationMarker,
  createNumberedPlaceMarker,
  createUserLocationContent,
  createUserLocationMarker,
} from "@/lib/maps/advancedMarkers";
import type { NavLatLng, NavPlaceOption, NavRoute } from "@/lib/api/navigation";
import type { MapState } from "@/lib/navigation/mapState";
import {
  CATEGORY_OVERVIEW_MAX_ZOOM,
  DESTINATION_VIEW_TILT,
  DESTINATION_VIEW_ZOOM,
  installMapSpeechSilencer,
  NAV_FOLLOW_TILT,
  NAV_IDLE_ZOOM,
  NAV_MAP_PADDING,
  NAV_ON_ROUTE_MAX_M,
  navigationFollowZoom,
  navigationHeading,
  navigationLookAheadCenter,
  remainingRouteAhead,
  ROUTE_PREVIEW_MIN_ZOOM,
  smoothHeading,
  smoothZoom,
  trackRouteProgress,
} from "@/lib/navigation/geo";

type DriveMapViewProps = {
  position: GeoPosition | null;
  route?: NavRoute | null;
  destinationPin?: { lat: number; lng: number; label: string } | null;
  placeOptions?: NavPlaceOption[];
  mapState: MapState;
  className?: string;
};

const DEFAULT_CENTER = { lat: 35.2271, lng: -80.8431 };
const ROUTE_STROKE = "#4285F4";

const MAP_STYLES: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#0a0a0a" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0a0a0a" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#9ca3af" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#1a1a2e" }] },
  {
    featureType: "road",
    elementType: "geometry.stroke",
    stylers: [{ color: "#334155" }],
  },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#16213e" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0e7490" }] },
  { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] },
];

function routePathPoints(
  route: NavRoute,
  position: GeoPosition | null,
): NavLatLng[] {
  if (route.path?.length > 1) return route.path;

  const steps = route.steps ?? [];
  if (steps.length > 0) {
    const pts: NavLatLng[] = [];
    for (const step of steps) {
      if (step.start) pts.push(step.start);
    }
    const last = steps[steps.length - 1];
    if (last?.end) pts.push(last.end);
    if (pts.length > 1) return pts;
  }

  if (position && route.destination) {
    return [
      { lat: position.lat, lng: position.lng },
      { lat: route.destination.lat, lng: route.destination.lng },
    ];
  }
  return [];
}

function remainingRoutePath(
  path: NavLatLng[],
  position: GeoPosition | null,
  lastIdx: number | null = null,
): NavLatLng[] {
  if (!position || path.length < 2) return path;
  return remainingRouteAhead(
    path,
    { lat: position.lat, lng: position.lng },
    lastIdx,
  );
}

function resetMapBearing(map: google.maps.Map) {
  map.setHeading(0);
  map.setTilt(0);
}

function applyMapAppearance(map: google.maps.Map, mapState: MapState) {
  const dark = { colorScheme: google.maps.ColorScheme.DARK };

  if (mapState === "destino_vista") {
    // ROADMAP vectorial + tilt: edificios extruded (mejor aproximación a flyover
    // sin Photorealistic 3D Tiles).
    map.setMapTypeId(google.maps.MapTypeId.ROADMAP);
    map.setOptions({
      ...dark,
      gestureHandling: "greedy",
      tilt: DESTINATION_VIEW_TILT,
      heading: 35,
    });
    return;
  }

  if (mapState === "ruta_lista") {
    map.setMapTypeId(google.maps.MapTypeId.ROADMAP);
    map.setOptions({
      ...dark,
      gestureHandling: "greedy",
      tilt: 48,
    });
    return;
  }

  if (mapState === "navegando") {
    map.setMapTypeId(google.maps.MapTypeId.ROADMAP);
    map.setOptions({
      ...dark,
      gestureHandling: "none",
      rotateControl: false,
      tilt: NAV_FOLLOW_TILT,
    });
    return;
  }

  map.setMapTypeId(google.maps.MapTypeId.ROADMAP);
  map.setOptions({ ...dark, gestureHandling: "greedy", tilt: 0, heading: 0 });
}

function moveCameraSafe(
  map: google.maps.Map,
  camera: {
    center: google.maps.LatLngLiteral;
    zoom: number;
    heading?: number;
    tilt?: number;
  },
) {
  if (typeof map.moveCamera === "function") {
    map.moveCamera(camera);
    return;
  }
  map.setCenter(camera.center);
  map.setZoom(camera.zoom);
  if (camera.heading != null) map.setHeading(camera.heading);
  if (camera.tilt != null) map.setTilt(camera.tilt);
}

function resetMapPadding(map: google.maps.Map) {
  map.setOptions({ padding: { top: 0, bottom: 0, left: 0, right: 0 } } as google.maps.MapOptions);
}

function applyNavigationMapPadding(map: google.maps.Map) {
  map.setOptions({ padding: { ...NAV_MAP_PADDING } } as google.maps.MapOptions);
}

/** Estado continuo de la cámara de navegación entre ticks GPS. */
type NavCameraState = {
  heading: number | null;
  zoom: number | null;
  routeIdx: number | null;
};

/** Cámara estilo Google Maps: zoom cercano, tilt 3D, rotación y look-ahead. */
function followNavigationCamera(
  map: google.maps.Map,
  position: GeoPosition,
  path: NavLatLng[],
  cam: NavCameraState,
): { heading: number; snapped: NavLatLng } {
  const user = { lat: position.lat, lng: position.lng };
  let snapped = user;
  let routeIdx: number | null = null;

  if (path.length >= 2) {
    const progress = trackRouteProgress(path, user, cam.routeIdx);
    routeIdx = progress.idx;
    // Fuera de ruta NO anclamos a una polilínea lejana — se vería un salto.
    snapped = progress.offRouteM <= NAV_ON_ROUTE_MAX_M ? progress.snapped : user;
  }

  const rawHeading = navigationHeading(
    user,
    path,
    position.heading,
    position.speed,
    cam.routeIdx,
  );
  const heading = smoothHeading(cam.heading, rawHeading, 30);
  const zoom = smoothZoom(cam.zoom, navigationFollowZoom(position.speed));
  cam.heading = heading;
  cam.zoom = zoom;
  cam.routeIdx = routeIdx;

  const center = navigationLookAheadCenter(
    snapped,
    path,
    heading,
    position.speed,
    routeIdx,
  );

  applyNavigationMapPadding(map);

  moveCameraSafe(map, {
    center,
    zoom,
    heading,
    tilt: NAV_FOLLOW_TILT,
  });
  // Refuerzo: algunos WebViews aplican tilt pero ignoran heading en un solo moveCamera.
  if (typeof map.setHeading === "function") {
    map.setHeading(heading);
  }
  if (typeof map.setTilt === "function") {
    map.setTilt(NAV_FOLLOW_TILT);
  }
  return { heading, snapped };
}

export function DriveMapView({
  position,
  route = null,
  destinationPin = null,
  placeOptions = [],
  mapState,
  className = "",
}: DriveMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null);
  const destMarkerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null);
  const placeMarkersRef = useRef<google.maps.marker.AdvancedMarkerElement[]>([]);
  const routePolylineRef = useRef<google.maps.Polyline | null>(null);
  const routeFittedRef = useRef(false);
  const searchFittedRef = useRef(false);
  const idleCenteredRef = useRef(false);
  const destViewReadyRef = useRef(false);
  const navCameraReadyRef = useRef(false);
  const navCamRef = useRef<NavCameraState>({
    heading: null,
    zoom: null,
    routeIdx: null,
  });
  const routePathRef = useRef<NavLatLng[]>([]);
  const routeIdentityRef = useRef<NavRoute | null>(null);
  const [mapsReady, setMapsReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    installMapSpeechSilencer();
  }, []);

  useEffect(() => {
    let cancelled = false;

    void loadGoogleMaps()
      .then(async () => {
        if (cancelled || !containerRef.current || mapRef.current) return;

        mapRef.current = new google.maps.Map(containerRef.current, {
          center: DEFAULT_CENTER,
          zoom: NAV_IDLE_ZOOM,
          mapId: CED_MAP_ID,
          mapTypeId: google.maps.MapTypeId.ROADMAP,
          colorScheme: google.maps.ColorScheme.DARK,
          backgroundColor: "#0a0a0a",
          styles: MAP_STYLES,
          disableDefaultUI: true,
          gestureHandling: "greedy",
          isFractionalZoomEnabled: true,
          // Vector + Map ID → tilt/heading (rotación tipo Waze).
          ...(typeof google.maps.RenderingType !== "undefined"
            ? { renderingType: google.maps.RenderingType.VECTOR }
            : {}),
        });

        markerRef.current = await createUserLocationMarker(mapRef.current, DEFAULT_CENTER);
        setMapsReady(true);
      })
      .catch((err: unknown) => {
        const msg =
          err instanceof Error ? err.message : "No se pudo cargar Google Maps.";
        setMapError(msg);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapsReady || !map) return;
    applyMapAppearance(map, mapState);

    if (mapState === "navegando") {
      applyNavigationMapPadding(map);
      // Solo el encuadre inicial al ENTRAR en navegación; el seguimiento
      // continuo lo lleva un único efecto (evita 2-3 llamadas por tick GPS
      // que anulaban el suavizado de heading).
      if (position && !navCameraReadyRef.current) {
        const path =
          routePathRef.current.length > 1
            ? routePathRef.current
            : route
              ? routePathPoints(route, position)
              : [];
        followNavigationCamera(map, position, path, navCamRef.current);
        navCameraReadyRef.current = true;
      }
    } else {
      resetMapPadding(map);
      navCameraReadyRef.current = false;
      navCamRef.current = { heading: null, zoom: null, routeIdx: null };
      if (mapState === "idle" || mapState === "searching") {
        resetMapBearing(map);
      }
    }
    if (mapState !== "searching") searchFittedRef.current = false;
    if (mapState !== "destino_vista") destViewReadyRef.current = false;
    if (mapState !== "ruta_lista") routeFittedRef.current = false;
    if (mapState === "idle") idleCenteredRef.current = false;
  }, [mapsReady, mapState, position?.lat, position?.lng, route]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapsReady || !map || !position || mapState !== "idle") return;
    if (!idleCenteredRef.current) {
      moveCameraSafe(map, {
        center: { lat: position.lat, lng: position.lng },
        zoom: NAV_IDLE_ZOOM,
        heading: 0,
        tilt: 0,
      });
      idleCenteredRef.current = true;
    }
  }, [mapsReady, mapState, position?.lat, position?.lng]);

  /** Comportamiento 1: lugar específico — cámara cercana inclinada sobre el POI. */
  useEffect(() => {
    const map = mapRef.current;
    if (!mapsReady || !map || mapState !== "destino_vista") return;
    const pin = destinationPin ?? route?.destination ?? null;
    if (!pin) return;
    if (destViewReadyRef.current) return;
    moveCameraSafe(map, {
      center: { lat: pin.lat, lng: pin.lng },
      zoom: DESTINATION_VIEW_ZOOM,
      heading: 35,
      tilt: DESTINATION_VIEW_TILT,
    });
    destViewReadyRef.current = true;
  }, [
    mapsReady,
    mapState,
    destinationPin?.lat,
    destinationPin?.lng,
    route?.destination?.lat,
    route?.destination?.lng,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (!map || !marker || !position) return;

    const latLng = { lat: position.lat, lng: position.lng };

    if (mapState === "navegando") {
      const path =
        routePathRef.current.length > 1
          ? routePathRef.current
          : route
            ? routePathPoints(route, position)
            : [];
      if (path.length > 1) routePathRef.current = path;
      // Driver ÚNICO del seguimiento: cámara y flecha usan el mismo heading
      // suavizado y la misma posición anclada — sin desfase entre ambos.
      const { heading, snapped } = followNavigationCamera(
        map,
        position,
        path,
        navCamRef.current,
      );
      navCameraReadyRef.current = true;
      marker.position = snapped;
      marker.content = createUserLocationContent(heading, true, true);
      return;
    }

    marker.position = latLng;
    marker.content = createUserLocationContent(position.heading, false, false);
  }, [
    position?.lat,
    position?.lng,
    position?.heading,
    position?.speed,
    mapState,
    route,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    for (const m of placeMarkersRef.current) m.map = null;
    placeMarkersRef.current = [];

    if (mapState !== "searching" || !placeOptions.length) return;

    let cancelled = false;
    void (async () => {
      const markers: google.maps.marker.AdvancedMarkerElement[] = [];
      for (let index = 0; index < placeOptions.length; index += 1) {
        const place = placeOptions[index]!;
        const marker = await createNumberedPlaceMarker(
          { lat: place.lat, lng: place.lng },
          map,
          index,
          place.name,
        );
        if (cancelled) {
          marker.map = null;
          return;
        }
        markers.push(marker);
      }
      if (!cancelled) placeMarkersRef.current = markers;
    })();

    if (!searchFittedRef.current) {
      const bounds = new google.maps.LatLngBounds();
      if (position) bounds.extend({ lat: position.lat, lng: position.lng });
      for (const place of placeOptions) {
        bounds.extend({ lat: place.lat, lng: place.lng });
      }
      map.fitBounds(bounds, 72);
      // Evita zoom demasiado cercano cuando hay pocas opciones lejanas.
      google.maps.event.addListenerOnce(map, "idle", () => {
        const z = map.getZoom();
        if (typeof z === "number" && z > CATEGORY_OVERVIEW_MAX_ZOOM) {
          map.setZoom(CATEGORY_OVERVIEW_MAX_ZOOM);
        }
        map.setTilt(0);
        map.setHeading(0);
      });
      searchFittedRef.current = true;
    }

    return () => {
      cancelled = true;
    };
  }, [mapState, placeOptions, position?.lat, position?.lng]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapsReady || !map || !route) return;
    if (mapState !== "ruta_lista" && mapState !== "navegando") return;

    const path = routePathPoints(route, position);
    if (path.length < 2) return;
    routePathRef.current = path;
    if (routeIdentityRef.current !== route) {
      // Ruta nueva o recalculada: el índice de progreso anterior ya no aplica.
      routeIdentityRef.current = route;
      navCamRef.current.routeIdx = null;
    }

    if (mapState === "ruta_lista") {
      if (routePolylineRef.current) {
        routePolylineRef.current.setPath(path);
      } else {
        routePolylineRef.current = new google.maps.Polyline({
          map,
          path,
          strokeColor: ROUTE_STROKE,
          strokeOpacity: 0.95,
          strokeWeight: 6,
          zIndex: 50,
        });
      }
      if (!routeFittedRef.current) {
        const dest = route.destination;
        if (dest) {
          // Preferir vista cercana al destino (no panorama de toda la ruta).
          moveCameraSafe(map, {
            center: { lat: dest.lat, lng: dest.lng },
            zoom: Math.max(ROUTE_PREVIEW_MIN_ZOOM + 1.5, 15.2),
            heading: 25,
            tilt: 48,
          });
        } else {
          const bounds = new google.maps.LatLngBounds();
          for (const p of path) bounds.extend(p);
          if (position) bounds.extend({ lat: position.lat, lng: position.lng });
          map.fitBounds(bounds, 56);
          google.maps.event.addListenerOnce(map, "idle", () => {
            const z = map.getZoom();
            if (typeof z === "number" && z < ROUTE_PREVIEW_MIN_ZOOM) {
              map.setZoom(ROUTE_PREVIEW_MIN_ZOOM);
            }
            map.setTilt(48);
          });
        }
        routeFittedRef.current = true;
      }
      return;
    }

    const drawPath =
      position && routePathRef.current.length > 1
        ? remainingRoutePath(
            routePathRef.current,
            position,
            navCamRef.current.routeIdx,
          )
        : path;

    if (routePolylineRef.current) {
      routePolylineRef.current.setPath(drawPath);
    } else {
      routePolylineRef.current = new google.maps.Polyline({
        map,
        path: drawPath,
        strokeColor: ROUTE_STROKE,
        strokeOpacity: 0.95,
        strokeWeight: 6,
        zIndex: 50,
      });
    }
  }, [mapsReady, route, mapState, position?.lat, position?.lng, position?.heading]);

  useEffect(() => {
    if (mapState !== "ruta_lista" && mapState !== "navegando") {
      if (routePolylineRef.current) {
        routePolylineRef.current.setMap(null);
        routePolylineRef.current = null;
      }
    }
  }, [mapState]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (destMarkerRef.current) {
      destMarkerRef.current.map = null;
      destMarkerRef.current = null;
    }

    const pin = destinationPin ?? route?.destination ?? null;
    if (
      !pin ||
      (mapState !== "ruta_lista" &&
        mapState !== "navegando" &&
        mapState !== "destino_vista")
    ) {
      return;
    }

    let cancelled = false;
    void createDestinationMarker(
      { lat: pin.lat, lng: pin.lng },
      map,
      "label" in pin ? pin.label : "Destino",
    ).then((marker) => {
      if (cancelled) {
        marker.map = null;
        return;
      }
      destMarkerRef.current = marker;
    });

    return () => {
      cancelled = true;
    };
  }, [destinationPin, route?.destination?.lat, route?.destination?.lng, mapState]);

  if (mapError) {
    return (
      <div
        className={`flex items-center justify-center bg-[#0b1220] p-6 text-center ${className}`}
      >
        <p className="max-w-sm text-sm text-red-300">{mapError}</p>
      </div>
    );
  }

  return <div ref={containerRef} className={`h-full w-full ${className}`} />;
}
