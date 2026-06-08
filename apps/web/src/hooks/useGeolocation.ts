"use client";

import { useEffect, useState } from "react";

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

const DEFAULT_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 5000,
  timeout: 20000,
};

export function useGeolocation(enabled = true): GeolocationState {
  const [position, setPosition] = useState<GeoPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!enabled) return;
    if (!navigator.geolocation) {
      setError("Tu dispositivo no soporta GPS.");
      setLoading(false);
      return;
    }

    const onSuccess = (pos: GeolocationPosition) => {
      setPosition({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        heading: pos.coords.heading,
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
      DEFAULT_OPTIONS,
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [enabled]);

  return { position, error, loading };
}
