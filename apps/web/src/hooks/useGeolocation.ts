"use client";

import { useEffect, useRef, useState } from "react";

export type GeoPosition = {
  lat: number;
  lng: number;
  accuracy: number;
  heading: number | null;
  speed: number | null;
};

type GeolocationState = {
  position: GeoPosition | null;
  error: string | null;
  loading: boolean;
};

const WATCH_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 1000,
  timeout: 5000,
};

function headingFromMovement(
  prev: { lat: number; lng: number } | null,
  next: { lat: number; lng: number },
): number | null {
  if (!prev) return null;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const toDeg = (rad: number) => ((rad * 180) / Math.PI + 360) % 360;
  const lat1 = toRad(prev.lat);
  const lat2 = toRad(next.lat);
  const dLng = toRad(next.lng - prev.lng);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) -
    Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  const dist = (next.lat - prev.lat) ** 2 + (next.lng - prev.lng) ** 2;
  if (dist < 1e-8) return null;
  return toDeg(Math.atan2(y, x));
}

export function useGeolocation(enabled = true): GeolocationState {
  const [position, setPosition] = useState<GeoPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const prevRef = useRef<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (!navigator.geolocation) {
      setError("Tu dispositivo no soporta GPS.");
      setLoading(false);
      return;
    }

    const onSuccess = (pos: GeolocationPosition) => {
      const coords = {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
      };
      const computedHeading = headingFromMovement(prevRef.current, coords);
      prevRef.current = coords;

      const heading =
        pos.coords.heading != null && !Number.isNaN(pos.coords.heading)
          ? pos.coords.heading
          : computedHeading;

      setPosition({
        lat: coords.lat,
        lng: coords.lng,
        accuracy: pos.coords.accuracy,
        heading,
        speed: pos.coords.speed,
      });
      setLoading(false);
      setError(null);
    };

    const onError = (err: GeolocationPositionError) => {
      const messages: Record<number, string> = {
        1: "Permiso de ubicación denegado. Actívalo para ver el mapa.",
        2: "No se pudo obtener tu ubicación.",
        3: "GPS tardó demasiado. Intenta de nuevo al aire libre.",
      };
      setError(messages[err.code] ?? err.message);
      setLoading(false);
    };

    const watchId = navigator.geolocation.watchPosition(
      onSuccess,
      onError,
      WATCH_OPTIONS,
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [enabled]);

  return { position, error, loading };
}
