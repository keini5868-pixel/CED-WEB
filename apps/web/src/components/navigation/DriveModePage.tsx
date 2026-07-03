"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { MapPin, Mic, Navigation } from "lucide-react";

import { CedVoiceControls } from "@/components/voice/CedVoiceControls";
import {
  CedHistoryPanel,
  CedSettingsModal,
  CedStopConfirmModal,
} from "@/components/voice/CedVoiceModals";
import { DriveMapView } from "@/components/navigation/DriveMapView";
import { NavigationPanel } from "@/components/navigation/NavigationPanel";
import { PlaceOptionsList } from "@/components/navigation/PlaceOptionsList";
import { SearchBar } from "@/components/navigation/SearchBar";
import { useGeolocation } from "@/hooks/useGeolocation";
import { useNavigationGuide } from "@/hooks/useNavigationGuide";
import { useCedVoiceSession } from "@/hooks/useCedVoiceSession";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import {
  cancelNavigation,
  computeNavigationRouteTo,
  fetchNavigationState,
  postNavigationLocation,
  searchNearbyPlaces,
  startNavigationOption,
  type NavPlaceOption,
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
    placeOptions: [],
    placeQuery: "",
  });
  const [navBusy, setNavBusy] = useState(false);
  const [navError, setNavError] = useState<string | null>(null);

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

  const applyRoute = useCallback((route: NavRoute) => {
    setNavError(null);
    setMapNav((prev) => ({
      ...prev,
      route,
      destinationPin: route.destination
        ? {
            lat: route.destination.lat,
            lng: route.destination.lng,
            label: route.destination.label,
          }
        : null,
      placeOptions: [],
      placeQuery: "",
    }));
  }, []);

  useEffect(() => {
    const syncRoute = async () => {
      try {
        const state = await fetchNavigationState(false);
        if (state.route) {
          applyRoute(state.route as NavRoute);
        }
        if (state.place_options?.length) {
          setMapNav((prev) => ({
            ...prev,
            placeOptions: state.place_options as NavPlaceOption[],
            placeQuery: state.place_query || "",
          }));
        }
      } catch {
        /* ignore */
      }
    };
    void syncRoute();
  }, [applyRoute]);

  useEffect(() => {
    const onNavEvent = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as {
        action?: string;
        payload?: unknown;
      };
      if (detail?.action === "apply_route" && detail.payload) {
        applyRoute(detail.payload as NavRoute);
      }
      if (detail?.action === "cancel_navigation") {
        setMapNav({
          route: null,
          destinationPin: null,
          placeOptions: [],
          placeQuery: "",
        });
      }
      if (detail?.action === "show_destination" && detail.payload) {
        const p = detail.payload as { lat: number; lng: number; label?: string };
        setMapNav((prev) => ({
          ...prev,
          route: null,
          destinationPin: {
            lat: p.lat,
            lng: p.lng,
            label: p.label || "Destino",
          },
        }));
      }
      if (detail?.action === "show_place_options" && detail.payload) {
        const p = detail.payload as { query?: string; places?: NavPlaceOption[] };
        setMapNav((prev) => ({
          ...prev,
          route: null,
          placeOptions: p.places || [],
          placeQuery: p.query || "",
        }));
      }
    };
    window.addEventListener("ced-navigation-event", onNavEvent);
    return () => window.removeEventListener("ced-navigation-event", onNavEvent);
  }, [applyRoute]);

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

  const handleSearch = async (query: string) => {
    setNavError(null);
    setNavBusy(true);
    try {
      const result = await searchNearbyPlaces(query);
      if (!result.ok || !result.places?.length) {
        setNavError(result.error || "No encontré lugares cerca.");
        return;
      }
      setMapNav((prev) => ({
        ...prev,
        route: null,
        placeOptions: result.places || [],
        placeQuery: result.query || query,
      }));
    } catch {
      setNavError("No pude buscar lugares cerca.");
    } finally {
      setNavBusy(false);
    }
  };

  const handlePlaceSelect = async (place: {
    lat: number;
    lng: number;
    label: string;
  }) => {
    setNavError(null);
    setNavBusy(true);
    try {
      const result = await computeNavigationRouteTo({
        lat: place.lat,
        lng: place.lng,
        label: place.label,
      });
      if (!result.ok || !result.route) {
        setNavError(result.error || "No pude calcular la ruta.");
        return;
      }
      applyRoute(result.route);
    } catch {
      setNavError("No pude iniciar la navegación.");
    } finally {
      setNavBusy(false);
    }
  };

  const handleStartOption = async (index: number) => {
    setNavError(null);
    setNavBusy(true);
    try {
      const result = await startNavigationOption(index);
      if (!result.ok || !result.route) {
        setNavError(result.error || "No pude iniciar el viaje.");
        return;
      }
      applyRoute(result.route);
    } catch {
      setNavError("No pude iniciar el viaje.");
    } finally {
      setNavBusy(false);
    }
  };

  const handleCancelOptions = () => {
    setMapNav((prev) => ({ ...prev, placeOptions: [], placeQuery: "" }));
    setNavError(null);
  };

  const handleStopNavigation = async () => {
    setNavBusy(true);
    try {
      await cancelNavigation();
      setNavError(null);
      setMapNav({
        route: null,
        destinationPin: null,
        placeOptions: [],
        placeQuery: "",
      });
    } finally {
      setNavBusy(false);
    }
  };

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

  const showOptions = mapNav.placeOptions.length > 0 && !mapNav.route;
  const showNavPanel = Boolean(mapNav.route);

  return (
    <div className="fixed inset-0 flex flex-col bg-black">
      <DriveMapView
        position={position}
        route={mapNav.route}
        destinationPin={mapNav.destinationPin}
        className="absolute inset-0"
      />

      <div className="pointer-events-none relative z-[110] flex h-full flex-col">
        <header className="pointer-events-auto flex items-start justify-between gap-2 bg-gradient-to-b from-black/90 to-transparent px-3 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-4">
          <Link
            href="/dashboard"
            className="rounded border border-cyan-500/40 bg-black/80 px-3 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-300 shadow-lg sm:text-xs"
          >
            ← VOLVER
          </Link>
          <div className="flex flex-col items-end gap-2">
            <button
              type="button"
              onClick={() => void voice.toggleMic()}
              disabled={voice.micBusy}
              className="pointer-events-auto rounded-full border border-cyan-400/50 bg-black/80 p-3 text-cyan-300 shadow-lg hover:bg-cyan-950/60 disabled:opacity-50"
              aria-label="Micrófono"
            >
              <Mic className={`h-5 w-5 ${voice.micOn ? "text-cyan-400" : ""}`} />
            </button>
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

        <div className="pointer-events-auto space-y-2 px-3 sm:px-4">
          {!showNavPanel ? (
            <>
              <SearchBar
                onSearch={(q) => void handleSearch(q)}
                onPlaceSelect={(p) => void handlePlaceSelect(p)}
                disabled={navBusy}
              />
              {navError ? (
                <p className="rounded bg-red-950/50 px-2 py-1 text-center text-xs text-red-300">
                  {navError}
                </p>
              ) : null}
              {showOptions ? (
                <PlaceOptionsList
                  query={mapNav.placeQuery}
                  places={mapNav.placeOptions}
                  onStart={(i) => void handleStartOption(i)}
                  onCancel={handleCancelOptions}
                  busy={navBusy}
                />
              ) : null}
            </>
          ) : null}
          {showNavPanel && mapNav.route ? (
            <NavigationPanel
              route={mapNav.route}
              position={position}
              onStop={() => void handleStopNavigation()}
              busy={navBusy}
            />
          ) : null}
        </div>

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
            Di: &quot;Llévame a Walmart&quot;, &quot;el primero&quot; o escribe arriba
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
