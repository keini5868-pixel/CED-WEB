"use client";

import { useCallback, useEffect, useState } from "react";

import {
  fetchMetaOAuthUrl,
  fetchMetaStatus,
  type MetaConnectionStatus,
} from "@/lib/api/meta";

export const META_CONNECTED_EVENT = "ced:meta-connected";

export function useConnectNetworks() {
  const [status, setStatus] = useState<MetaConnectionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await fetchMetaStatus();
    if (data) setStatus(data);
  }, []);

  useEffect(() => {
    void refresh();
    const onConnected = () => void refresh();
    window.addEventListener(META_CONNECTED_EVENT, onConnected);
    return () => window.removeEventListener(META_CONNECTED_EVENT, onConnected);
  }, [refresh]);

  const connect = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const { url, error: oauthError } = await fetchMetaOAuthUrl();
      if (!url) {
        setError(
          oauthError || "No se pudo iniciar OAuth. ¿API activa y META configurado?",
        );
        return;
      }
      window.location.href = url;
    } catch {
      setError("Error al conectar con Meta.");
    } finally {
      setBusy(false);
    }
  }, []);

  return { status, busy, error, connect, refresh };
}
