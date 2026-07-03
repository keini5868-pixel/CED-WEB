"use client";

import { useEffect, useRef, useState } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import { loadGoogleMaps } from "@/lib/maps/loadGoogleMaps";
import type { NavLatLng, NavPlaceOption, NavRoute } from "@/lib/api/navigation";
import type { MapState } from "@/lib/navigation/mapState";
import { closestPathIndex } from "@/lib/navigation/geo";

type DriveMapViewProps = {
  position: GeoPosition | null;
  route?: NavRoute | null;
  destinationPin?: { lat: number; lng: number; label: string } | null;
  placeOptions?: NavPlaceOption[];
  mapState: MapState;
  className?: string;
};

const DEFAULT_CENTER = { lat: 35.2271, lng: -80.8431 };

const MAP_STYLES: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#0a0a0a" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0a0a0a" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#00ffff" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#1a1a2e" }] },
  {
    featureType: "road",
    elementType: "geometry.stroke",
    stylers: [{ color: "#00ffff" }],
  },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#16213e" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0e7490" }] },
  { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] },
];

function userIcon(
  google: typeof globalThis.google,
  heading: number | null,
  navigating: boolean,
): google.maps.Symbol {
  if (navigating) {
    return {
      path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
      scale: 5,
      fillColor: "#00ffff",
      fillOpacity: 1,
      strokeColor: "#ffffff",
      strokeWeight: 1,
      rotation: heading ?? 0,
    };
  }
  return {
    path: google.maps.SymbolPath.CIRCLE,
    scale: 10,
    fillColor: "#00e5ff",
    fillOpacity: 1,
    strokeColor: "#ffffff",
    strokeWeight: 2,
  };
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
  const markerRef = useRef<google.maps.Marker | null>(null);
  const destMarkerRef = useRef<google.maps.Marker | null>(null);
  const placeMarkersRef = useRef<google.maps.Marker[]>([]);
  const routePolylineRef = useRef<google.maps.Polyline | null>(null);
  const consumedPolylineRef = useRef<google.maps.Polyline | null>(null);
  const routeFittedRef = useRef(false);
  const searchFittedRef = useRef(false);
  const idleCenteredRef = useRef(false);
  const [mapError, setMapError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void loadGoogleMaps()
      .then((google) => {
        if (cancelled || !containerRef.current || mapRef.current) return;

        mapRef.current = new google.maps.Map(containerRef.current, {
          center: DEFAULT_CENTER,
          zoom: 15,
          disableDefaultUI: false,
          zoomControl: true,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
          gestureHandling: "greedy",
          styles: MAP_STYLES,
        });

        markerRef.current = new google.maps.Marker({
          map: mapRef.current,
          position: DEFAULT_CENTER,
          title: "Tu ubicación",
          icon: userIcon(google, null, false),
          zIndex: 999,
        });
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
    if (mapState !== "navigating") routeFittedRef.current = false;
    if (mapState !== "searching") searchFittedRef.current = false;
    if (mapState === "idle") idleCenteredRef.current = false;
  }, [mapState]);

  useEffect(() => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (!map || !marker || !position) return;

    const latLng = { lat: position.lat, lng: position.lng };
    marker.setPosition(latLng);
    marker.setIcon(userIcon(google, position.heading, mapState === "navigating"));

    if (mapState === "navigating") {
      map.panTo(latLng);
      return;
    }

    if (mapState === "idle" && !idleCenteredRef.current) {
      map.panTo(latLng);
      idleCenteredRef.current = true;
    }
  }, [position, mapState]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    for (const m of placeMarkersRef.current) m.setMap(null);
    placeMarkersRef.current = [];

    if (mapState !== "searching" || !placeOptions.length) return;

    placeOptions.forEach((place, index) => {
      const marker = new google.maps.Marker({
        map,
        position: { lat: place.lat, lng: place.lng },
        title: place.name,
        label: {
          text: String(index + 1),
          color: "#0a0a0a",
          fontWeight: "700",
        },
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 9,
          fillColor: "#a855f7",
          fillOpacity: 0.95,
          strokeColor: "#ffffff",
          strokeWeight: 1.5,
        },
        zIndex: 100 + index,
      });
      placeMarkersRef.current.push(marker);
    });

    if (!searchFittedRef.current) {
      const bounds = new google.maps.LatLngBounds();
      if (position) bounds.extend({ lat: position.lat, lng: position.lng });
      for (const place of placeOptions) {
        bounds.extend({ lat: place.lat, lng: place.lng });
      }
      map.fitBounds(bounds, 56);
      searchFittedRef.current = true;
    }
  }, [mapState, placeOptions, position?.lat, position?.lng]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (routePolylineRef.current) {
      routePolylineRef.current.setMap(null);
      routePolylineRef.current = null;
    }
    if (consumedPolylineRef.current) {
      consumedPolylineRef.current.setMap(null);
      consumedPolylineRef.current = null;
    }

    const path: NavLatLng[] = route?.path?.length ? route.path : [];
    if (path.length < 2 || mapState !== "navigating") return;

    let remaining = path;
    let consumed: NavLatLng[] = [];
    if (position) {
      const idx = closestPathIndex(path, position);
      consumed = path.slice(0, idx + 1);
      remaining = path.slice(idx);
    }

    if (consumed.length > 1) {
      consumedPolylineRef.current = new google.maps.Polyline({
        map,
        path: consumed,
        strokeColor: "#334155",
        strokeOpacity: 0.55,
        strokeWeight: 4,
      });
    }

    if (remaining.length > 1) {
      routePolylineRef.current = new google.maps.Polyline({
        map,
        path: remaining,
        strokeColor: "#00e5ff",
        strokeOpacity: 0.95,
        strokeWeight: 5,
      });
    }

    if (!routeFittedRef.current) {
      const bounds = new google.maps.LatLngBounds();
      for (const p of path) bounds.extend(p);
      if (position) bounds.extend({ lat: position.lat, lng: position.lng });
      map.fitBounds(bounds, 48);
      routeFittedRef.current = true;
    }
  }, [route, mapState, position?.lat, position?.lng]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (destMarkerRef.current) {
      destMarkerRef.current.setMap(null);
      destMarkerRef.current = null;
    }

    const pin = destinationPin ?? route?.destination ?? null;
    if (!pin || mapState !== "navigating") return;

    destMarkerRef.current = new google.maps.Marker({
      map,
      position: { lat: pin.lat, lng: pin.lng },
      title: "label" in pin ? pin.label : "Destino",
      icon: {
        path: google.maps.SymbolPath.BACKWARD_CLOSED_ARROW,
        scale: 6,
        fillColor: "#a855f7",
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 1.5,
        rotation: 180,
      },
    });
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
