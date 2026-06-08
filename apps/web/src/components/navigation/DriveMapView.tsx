"use client";

import { useEffect, useRef, useState } from "react";

import type { GeoPosition } from "@/hooks/useGeolocation";
import { loadGoogleMaps } from "@/lib/maps/loadGoogleMaps";

type DriveMapViewProps = {
  position: GeoPosition | null;
  className?: string;
};

const DEFAULT_CENTER = { lat: 19.4326, lng: -99.1332 };

const MAP_STYLES: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#0b1220" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#8ec3e6" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0b1220" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#1a2a44" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#2a4368" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0e7490" }] },
  { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] },
];

export function DriveMapView({ position, className = "" }: DriveMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markerRef = useRef<google.maps.Marker | null>(null);
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
          fullscreenControl: true,
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
