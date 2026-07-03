"use client";

import { useEffect, useRef, useState } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import { loadGoogleMaps } from "@/lib/maps/loadGoogleMaps";
import type { NavLatLng, NavRoute } from "@/lib/api/navigation";

type DriveMapViewProps = {
  position: GeoPosition | null;
  route?: NavRoute | null;
  destinationPin?: { lat: number; lng: number; label: string } | null;
  className?: string;
};

const DEFAULT_CENTER = { lat: 19.4326, lng: -99.1332 };

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

export function DriveMapView({
  position,
  route = null,
  destinationPin = null,
  className = "",
}: DriveMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markerRef = useRef<google.maps.Marker | null>(null);
  const destMarkerRef = useRef<google.maps.Marker | null>(null);
  const polylineRef = useRef<google.maps.Polyline | null>(null);
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
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: "#00e5ff",
            fillOpacity: 1,
            strokeColor: "#ffffff",
            strokeWeight: 2,
          },
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
    if (!position || !mapRef.current || !markerRef.current) return;
    const latLng = { lat: position.lat, lng: position.lng };
    markerRef.current.setPosition(latLng);
    mapRef.current.panTo(latLng);
  }, [position]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (polylineRef.current) {
      polylineRef.current.setMap(null);
      polylineRef.current = null;
    }

    const path: NavLatLng[] = route?.path?.length ? route.path : [];
    if (path.length > 1) {
      polylineRef.current = new google.maps.Polyline({
        map,
        path,
        strokeColor: "#00e5ff",
        strokeOpacity: 0.9,
        strokeWeight: 5,
      });
      const bounds = new google.maps.LatLngBounds();
      for (const p of path) bounds.extend(p);
      map.fitBounds(bounds, 48);
    }
  }, [route]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (destMarkerRef.current) {
      destMarkerRef.current.setMap(null);
      destMarkerRef.current = null;
    }

    const pin = destinationPin ?? route?.destination ?? null;
    if (!pin) return;

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
  }, [destinationPin, route?.destination?.lat, route?.destination?.lng]);

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
