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
  closestPathIndex,
  installMapSpeechSilencer,
  NAV_FOLLOW_TILT,
  NAV_IDLE_ZOOM,
  NAV_MAP_PADDING,
  navigationFollowZoom,
  navigationHeading,
  navigationLookAheadCenter,
  smoothHeading,
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
): NavLatLng[] {
  if (!position || path.length < 2) return path;
  const idx = closestPathIndex(path, position);
  let remaining = path.slice(idx);
  if (remaining.length < 2) {
    remaining = [
      { lat: position.lat, lng: position.lng },
      ...(remaining.length ? remaining : [path[path.length - 1]!]),
    ];
  }
  return remaining;
}

function resetMapBearing(map: google.maps.Map) {
  map.setHeading(0);
  map.setTilt(0);
}

function applyMapAppearance(map: google.maps.Map, mapState: MapState) {
  const dark = { colorScheme: google.maps.ColorScheme.DARK };

  if (mapState === "ruta_lista") {
    map.setMapTypeId(google.maps.MapTypeId.SATELLITE);
    map.setOptions({ ...dark, gestureHandling: "greedy" });
    return;
  }

  if (mapState === "navegando") {
    // ROADMAP vectorial + tilt: muestra edificios 3D extruded (HYBRID oculta relief urbano).
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
  map.setOptions({ ...dark, gestureHandling: "greedy" });
}

function resetMapPadding(map: google.maps.Map) {
  map.setOptions({ padding: { top: 0, bottom: 0, left: 0, right: 0 } } as google.maps.MapOptions);
}

function applyNavigationMapPadding(map: google.maps.Map) {
  map.setOptions({ padding: { ...NAV_MAP_PADDING } } as google.maps.MapOptions);
}

/** Cámara estilo Google Maps: zoom cercano, tilt 3D, rotación y look-ahead. */
function followNavigationCamera(
  map: google.maps.Map,
  position: GeoPosition,
  path: NavLatLng[],
  lastHeadingRef: { current: number | null },
) {
  const user = { lat: position.lat, lng: position.lng };
  const rawHeading = navigationHeading(user, path, position.heading, position.speed);
  const heading = smoothHeading(lastHeadingRef.current, rawHeading);
  lastHeadingRef.current = heading;
  const zoom = navigationFollowZoom(position.speed);
  const center = navigationLookAheadCenter(user, path, heading, position.speed);

  applyNavigationMapPadding(map);

  const camera = {
    center,
    zoom,
    heading,
    tilt: NAV_FOLLOW_TILT,
  };

  if (typeof map.moveCamera === "function") {
    map.moveCamera(camera);
    return;
  }

  map.setCenter(center);
  map.setZoom(zoom);
  map.setHeading(heading);
  map.setTilt(NAV_FOLLOW_TILT);
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
  const navCameraReadyRef = useRef(false);
  const lastNavHeadingRef = useRef<number | null>(null);
  const routePathRef = useRef<NavLatLng[]>([]);
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

    if (mapState !== "navegando") {
      routeFittedRef.current = false;
      navCameraReadyRef.current = false;
      lastNavHeadingRef.current = null;
      routePathRef.current = [];
      resetMapBearing(map);
      resetMapPadding(map);
    } else {
      applyNavigationMapPadding(map);
      if (position) {
        const path =
          routePathRef.current.length > 1
            ? routePathRef.current
            : route
              ? routePathPoints(route, position)
              : [];
        followNavigationCamera(map, position, path, lastNavHeadingRef);
        navCameraReadyRef.current = true;
      }
    }
    if (mapState !== "searching") searchFittedRef.current = false;
    if (mapState === "idle") idleCenteredRef.current = false;
  }, [mapsReady, mapState, position?.lat, position?.lng, route]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapsReady || !map || !position || mapState !== "idle") return;
    if (!idleCenteredRef.current) {
      map.setZoom(NAV_IDLE_ZOOM);
      map.setTilt(0);
      map.setHeading(0);
      map.panTo({ lat: position.lat, lng: position.lng });
      idleCenteredRef.current = true;
    }
  }, [mapsReady, mapState, position?.lat, position?.lng]);

  useEffect(() => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (!map || !marker || !position) return;

    const latLng = { lat: position.lat, lng: position.lng };
    marker.position = latLng;

    if (mapState === "navegando") {
      const path =
        routePathRef.current.length > 1
          ? routePathRef.current
          : route
            ? routePathPoints(route, position)
            : [];
      const heading = navigationHeading(latLng, path, position.heading, position.speed);
      followNavigationCamera(map, position, path, lastNavHeadingRef);
      navCameraReadyRef.current = true;
      marker.content = createUserLocationContent(heading, true, true);
      return;
    }

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
    if (!map || mapState !== "navegando" || !position) return;
    const path =
      routePathRef.current.length > 1
        ? routePathRef.current
        : route
          ? routePathPoints(route, position)
          : [];
    if (path.length < 2) return;
    followNavigationCamera(map, position, path, lastNavHeadingRef);
  }, [mapState, route, position?.lat, position?.lng, position?.heading]);

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
      map.fitBounds(bounds, 56);
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
        const bounds = new google.maps.LatLngBounds();
        for (const p of path) bounds.extend(p);
        if (position) bounds.extend({ lat: position.lat, lng: position.lng });
        if (route.destination) {
          bounds.extend({ lat: route.destination.lat, lng: route.destination.lng });
        }
        map.fitBounds(bounds, 56);
        routeFittedRef.current = true;
      }
      return;
    }

    const drawPath =
      position && routePathRef.current.length > 1
        ? remainingRoutePath(routePathRef.current, position)
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
    if (!pin || (mapState !== "ruta_lista" && mapState !== "navegando")) return;

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
