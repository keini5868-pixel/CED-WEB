"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MapPin, Navigation } from "lucide-react";

import { CedVoiceControls } from "@/components/voice/CedVoiceControls";
import {
  CedHistoryPanel,
  CedSettingsModal,
  CedStopConfirmModal,
} from "@/components/voice/CedVoiceModals";
import { DriveMapView } from "@/components/navigation/DriveMapView";
import { useGeolocation } from "@/hooks/useGeolocation";
import { useNavigationGuide } from "@/hooks/useNavigationGuide";
import { useCedVoiceSession } from "@/hooks/useCedVoiceSession";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import {
  fetchNavigationState,
  postNavigationLocation,
  type NavRoute,
} from "@/lib/api/navigation";
import type { NavigationMapState } from "@/lib/api/navigation";
import { prefetchEphemeralToken } from "@/lib/voice/ephemeralTokenCache";

export function DriveModePage() {
  const { refresh: refreshUsage } = useUsageBalance();
  const { position, error: geoError, loading: geoLoading } = useGeolocation(true);
  const voice = useCedVoiceSession(refreshUsage);
  const [mapNav, setMapNav] = useState<NavigationMapState>({
    route: null,
    destinationPin: null,
  });

  useNavigationGuide({
    position,
    route: mapNav.route,
    enabled: voice.micOn && Boolean(mapNav.route),
  });

  useEffect(() => {
    prefetchEphemeralToken();
  }, []);

  useEffect(() => {
    if (!position) return;
    void postNavigationLocation({
      lat: position.lat,
      lng: position.lng,
      heading: position.heading,
      speed: position.speed,
      accuracy: position.accuracy,
    });
  }, [position]);

  useEffect(() => {
    const syncRoute = async () => {
      try {
        const state = await fetchNavigationState(false);
        if (state.route) {
          setMapNav({
            route: state.route as NavRoute,
            destinationPin: state.route.destination
              ? {
                  lat: state.route.destination.lat,
                  lng: state.route.destination.lng,
                  label: state.route.destination.label,
                }
              : null,
          });
        }
      } catch {
        /* ignore */
      }
    };
    void syncRoute();
  }, []);

  useEffect(() => {
    const onNavEvent = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as { action?: string; payload?: unknown };
      if (detail?.action === "apply_route" && detail.payload) {
        const route = detail.payload as NavRoute;
        setMapNav({
          route,
          destinationPin: route.destination
            ? {
                lat: route.destination.lat,
                lng: route.destination.lng,
                label: route.destination.label,
              }
            : null,
        });
      }
      if (detail?.action === "cancel_navigation") {
        setMapNav({ route: null, destinationPin: null });
      }
      if (detail?.action === "show_destination" && detail.payload) {
        const p = detail.payload as { lat: number; lng: number; label?: string };
        setMapNav({
          route: null,
          destinationPin: {
            lat: p.lat,
            lng: p.lng,
            label: p.label || "Destino",
          },
        });
      }
    };
    window.addEventListener("ced-navigation-event", onNavEvent);
    return () => window.removeEventListener("ced-navigation-event", onNavEvent);
  }, []);

  useEffect(() => {
    type WakeLockSentinel = { release: () => Promise<void> };
    let wakeLock: WakeLockSentinel | null = null;
    const requestWake = async () => {
      try {
        if ("wakeLock" in navigator && document.visibilityState === "visible") {
          wakeLock = await navigator.wakeLock.request("screen");
        }
      } catch {
        /* ignore */
      }
    };
    void requestWake();
    const onVisible = () => {
      if (document.visibilityState === "visible") void requestWake();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      void wakeLock?.release();
    };
  }, []);

  const gpsLabel = geoLoading
    ? "Buscando GPS…"
    : geoError
      ? "GPS off"
      : position
        ? `±${Math.round(position.accuracy)} m`
        : "GPS…";

  const routeLabel = mapNav.route
    ? `${mapNav.route.duration_text} · ${mapNav.route.distance_text}`
    : null;

  return (
    <div className="fixed inset-0 flex flex-col bg-black">
      <DriveMapView
        position={position}
        route={mapNav.route}
        destinationPin={mapNav.destinationPin}
        className="absolute inset-0"
      />

      <div className="pointer-events-none relative z-[110] flex h-full flex-col">
        <header className="pointer-events-auto flex items-center justify-between gap-2 bg-gradient-to-b from-black/90 to-transparent px-3 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-4">
          <Link
            href="/dashboard"
            className="rounded border border-cyan-500/40 bg-black/80 px-3 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-300 shadow-lg sm:text-xs"
          >
            ← VOLVER
          </Link>
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2 rounded border border-cyan-500/30 bg-black/70 px-2 py-1.5">
              <MapPin className="h-3.5 w-3.5 text-cyan-400" />
              <span className="text-[10px] text-cyan-200 sm:text-xs">{gpsLabel}</span>
            </div>
            {routeLabel ? (
              <span className="max-w-[200px] truncate rounded bg-purple-900/50 px-2 py-0.5 text-[10px] text-purple-200">
                {mapNav.route?.destination.label} · {routeLabel}
              </span>
            ) : null}
          </div>
        </header>

        <div className="flex-1" />

        <div className="pointer-events-auto border-t border-cyan-500/25 bg-black/85 px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md sm:px-4">
          <div className="mb-2 flex items-center gap-2">
            <Navigation className="h-4 w-4 text-cyan-400" />
            <p className="font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-widest text-cyan-300">
              MODO CONDUCIR · GPS + GUÍA
            </p>
          </div>

          <p className="mb-3 text-center font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wide text-[#00e5ff]">
            {voice.statusLabel}
          </p>

          {geoError ? (
            <p className="mb-2 text-center text-xs text-amber-300">{geoError}</p>
          ) : null}

          {voice.errorMessage ? (
            <p className="mb-2 text-center text-xs text-red-300">{voice.errorMessage}</p>
          ) : null}

          <CedVoiceControls
            micOn={voice.micOn}
            micBusy={voice.micBusy}
            cameraOn={voice.cameraOn}
            muted={voice.muted}
            paused={voice.paused}
            onMic={() => void voice.toggleMic()}
            onCamera={() => void voice.toggleCamera()}
            onMute={() => voice.setMuted((m) => !m)}
            onPause={voice.togglePause}
            onStop={() => voice.setStopConfirmOpen(true)}
            onHistory={() => voice.setHistoryOpen(true)}
            onChat={() => undefined}
            onSettings={() => voice.setSettingsOpen(true)}
            onFiles={() => undefined}
          />

          <p className="mt-2 text-center text-[10px] text-cyan-600">
            Di: &quot;Abre el mapa&quot;, &quot;guíame a [dirección]&quot; o &quot;busca [lugar]&quot;
          </p>
        </div>
      </div>

      <CedStopConfirmModal
        open={voice.stopConfirmOpen}
        onClose={() => voice.setStopConfirmOpen(false)}
        onConfirm={() => {
          voice.stopSession();
          voice.setStopConfirmOpen(false);
        }}
      />
      <CedSettingsModal
        open={voice.settingsOpen}
        onClose={() => voice.setSettingsOpen(false)}
        prefs={voice.prefs}
        onSave={voice.updatePrefs}
        micOn={voice.micOn}
        onApplyVoice={voice.applyVoiceChange}
      />
      <CedHistoryPanel
        open={voice.historyOpen}
        onClose={() => voice.setHistoryOpen(false)}
      />
    </div>
  );
}
