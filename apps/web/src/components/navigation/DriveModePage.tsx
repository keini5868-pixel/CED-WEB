"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { MapPin, Navigation, X } from "lucide-react";

import { DriveMapView } from "@/components/navigation/DriveMapView";
import { NavigationPanel } from "@/components/navigation/NavigationPanel";
import { PlaceOptionsList } from "@/components/navigation/PlaceOptionsList";
import { RoutePreviewPanel } from "@/components/navigation/RoutePreviewPanel";
import { SearchBar } from "@/components/navigation/SearchBar";
import { useDriveMap } from "@/contexts/DriveMapContext";
import { useGeolocation } from "@/hooks/useGeolocation";
import { useNavigationGuide } from "@/hooks/useNavigationGuide";
import {
  cancelNavigation,
  computeNavigationRouteTo,
  fetchNavigationState,
  postNavigationBegin,
  postNavigationLocation,
  searchNearbyPlaces,
  startNavigationOption,
  type NavPlaceOption,
  type NavRoute,
} from "@/lib/api/navigation";
import type { NavigationMapState } from "@/lib/api/navigation";
import { MAP_UI_VISIBILITY, deriveMapState } from "@/lib/navigation/mapState";
import { cancelBrowserNavigationSpeech } from "@/lib/navigation/geo";

const EMPTY_NAV: NavigationMapState = {
  route: null,
  destinationPin: null,
  placeOptions: [],
  placeQuery: "",
  isNavigating: false,
};

type DriveModePageProps = {
  /** Overlay sobre el dashboard — la sesión de voz de CedVoiceHub sigue activa debajo. */
  embedded?: boolean;
  onClose?: () => void;
};

export function DriveModePage({ embedded = false, onClose }: DriveModePageProps) {
  const { closeDriveMap, registerMapVoiceHandlers, consumeBootstrapAction } =
    useDriveMap();
  const closeMap = onClose ?? closeDriveMap;
  const { position, error: geoError, loading: geoLoading } = useGeolocation(true);
  const [mapNav, setMapNav] = useState<NavigationMapState>(EMPTY_NAV);
  const [navBusy, setNavBusy] = useState(false);
  const [navError, setNavError] = useState<string | null>(null);

  const mapState = useMemo(
    () =>
      deriveMapState({
        route: mapNav.route,
        placeOptions: mapNav.placeOptions,
        isSearching: navBusy && !mapNav.route,
        isNavigating: mapNav.isNavigating,
      }),
    [mapNav.route, mapNav.placeOptions, mapNav.isNavigating, navBusy],
  );

  const ui = MAP_UI_VISIBILITY[mapState];

  const resetToIdle = useCallback(() => {
    cancelBrowserNavigationSpeech();
    setNavError(null);
    setMapNav(EMPTY_NAV);
  }, []);

  const prepareRoute = useCallback((route: NavRoute) => {
    cancelBrowserNavigationSpeech();
    setNavError(null);
    setMapNav({
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
      isNavigating: false,
    });
  }, []);

  const beginNavigation = useCallback(() => {
    cancelBrowserNavigationSpeech();
    setMapNav((prev) =>
      prev.route ? { ...prev, isNavigating: true, placeOptions: [], placeQuery: "" } : prev,
    );
    void postNavigationBegin();
  }, []);

  const applyRouteFromServer = useCallback((route: NavRoute) => {
    cancelBrowserNavigationSpeech();
    setNavError(null);
    setMapNav((prev) => {
      if (prev.isNavigating) return prev;
      return {
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
        isNavigating: false,
      };
    });
  }, []);

  const handleStopNavigation = useCallback(async () => {
    setNavBusy(true);
    try {
      await cancelNavigation();
      resetToIdle();
    } finally {
      setNavBusy(false);
    }
  }, [resetToIdle]);

  const tryApplyRouteFromServer = useCallback(async (): Promise<NavRoute | null> => {
    try {
      const state = await fetchNavigationState(false);
      return (state.route as NavRoute | null | undefined) ?? null;
    } catch {
      return null;
    }
  }, []);

  const handleSearch = useCallback(async (query: string) => {
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
        destinationPin: null,
        placeOptions: result.places || [],
        placeQuery: result.query || query,
      }));
    } catch {
      setNavError("No pude buscar lugares cerca.");
    } finally {
      setNavBusy(false);
    }
  }, []);

  const handlePlaceSelect = useCallback(
    async (place: { lat: number; lng: number; label: string }) => {
      setNavError(null);
      setNavBusy(true);
      try {
        const result = await computeNavigationRouteTo({
          lat: place.lat,
          lng: place.lng,
          label: place.label,
        });
        if (result.ok && result.route) {
          prepareRoute(result.route);
          return;
        }
        const synced = await tryApplyRouteFromServer();
        if (synced) {
          prepareRoute(synced);
          return;
        }
        setNavError(result.error || "No pude calcular la ruta.");
      } catch {
        const synced = await tryApplyRouteFromServer();
        if (synced) {
          prepareRoute(synced);
          return;
        }
        setNavError("No pude iniciar la navegación.");
      } finally {
        setNavBusy(false);
      }
    },
    [prepareRoute, tryApplyRouteFromServer],
  );

  const handleStartOption = useCallback(
    async (index: number) => {
      setNavError(null);
      setNavBusy(true);
      try {
        const result = await startNavigationOption(index);
        if (result.ok && result.route) {
          prepareRoute(result.route);
          return;
        }
        const synced = await tryApplyRouteFromServer();
        if (synced) {
          prepareRoute(synced);
          return;
        }
        setNavError(result.error || "No pude iniciar el viaje.");
      } catch {
        const synced = await tryApplyRouteFromServer();
        if (synced) {
          prepareRoute(synced);
          return;
        }
        setNavError("No pude iniciar el viaje.");
      } finally {
        setNavBusy(false);
      }
    },
    [prepareRoute, tryApplyRouteFromServer],
  );

  const handleCancelOptions = useCallback(() => {
    setMapNav((prev) => ({ ...prev, placeOptions: [], placeQuery: "" }));
    setNavError(null);
  }, []);

  const getRouteSummary = useCallback((): string | null => {
    if (!mapNav.route) return null;
    return `${mapNav.route.duration_text} · ${mapNav.route.distance_text} hacia ${mapNav.route.destination.label}`;
  }, [mapNav.route]);

  useNavigationGuide({
    position,
    route: mapNav.route,
    enabled: mapState === "navegando",
    onArrival: () => {
      void handleStopNavigation();
    },
  });

  useEffect(() => {
    if (mapState === "navegando") {
      cancelBrowserNavigationSpeech();
    }
  }, [mapState]);

  useEffect(() => {
    if (!position) return;
    void postNavigationLocation({
      lat: position.lat,
      lng: position.lng,
      heading: position.heading,
      speed: position.speed,
      accuracy: position.accuracy,
      is_navigating: mapState === "navegando",
    });
  }, [position, mapState]);

  useEffect(() => {
    const syncRoute = async () => {
      try {
        const state = await fetchNavigationState(false);
        if (state.route) {
          applyRouteFromServer(state.route as NavRoute);
          return;
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
  }, [applyRouteFromServer]);

  useEffect(() => {
    registerMapVoiceHandlers({
      searchPlace: handleSearch,
      selectOption: handleStartOption,
      startNavigation: beginNavigation,
      stopNavigation: handleStopNavigation,
      getRouteSummary,
    });
    return () => registerMapVoiceHandlers(null);
  }, [
    registerMapVoiceHandlers,
    handleSearch,
    handleStartOption,
    beginNavigation,
    handleStopNavigation,
    getRouteSummary,
  ]);

  useEffect(() => {
    const processNavAction = (detail: { action?: string; payload?: unknown }) => {
      if (detail?.action === "apply_route" && detail.payload) {
        applyRouteFromServer(detail.payload as NavRoute);
      }
      if (detail?.action === "begin_navigation") {
        beginNavigation();
      }
      if (detail?.action === "cancel_navigation") {
        resetToIdle();
      }
      if (detail?.action === "close_drive") {
        closeMap();
      }
      if (detail?.action === "show_destination" && detail.payload) {
        const p = detail.payload as { lat: number; lng: number; label?: string };
        setMapNav((prev) => ({
          ...prev,
          route: null,
          isNavigating: false,
          destinationPin: {
            lat: p.lat,
            lng: p.lng,
            label: p.label || "Destino",
          },
          placeOptions: [],
          placeQuery: "",
        }));
      }
      if (detail?.action === "show_place_options" && detail.payload) {
        const p = detail.payload as { query?: string; places?: NavPlaceOption[] };
        setNavError(null);
        setMapNav((prev) => ({
          ...prev,
          route: null,
          isNavigating: false,
          destinationPin: null,
          placeOptions: p.places || [],
          placeQuery: p.query || "",
        }));
      }
    };

    const bootstrap = consumeBootstrapAction();
    if (bootstrap) {
      processNavAction(bootstrap);
    }

    const onNavEvent = (ev: Event) => {
      processNavAction((ev as CustomEvent).detail as { action?: string; payload?: unknown });
    };
    window.addEventListener("ced-navigation-event", onNavEvent);
    return () => window.removeEventListener("ced-navigation-event", onNavEvent);
  }, [
    applyRouteFromServer,
    beginNavigation,
    resetToIdle,
    closeMap,
    consumeBootstrapAction,
  ]);

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

  return (
    <div className="fixed inset-0 flex flex-col bg-black">
      <DriveMapView
        position={position}
        route={mapNav.route}
        destinationPin={mapNav.destinationPin}
        placeOptions={mapNav.placeOptions}
        mapState={mapState}
        className="absolute inset-0"
      />

      {ui.navPanel && mapNav.route ? (
        <div className="pointer-events-auto absolute left-0 right-0 top-0 z-[120]">
          <NavigationPanel
            route={mapNav.route}
            position={position}
            onStop={() => void handleStopNavigation()}
            busy={navBusy}
          />
        </div>
      ) : null}

      <div className="pointer-events-none relative z-[110] flex h-full flex-col">
        {mapState !== "navegando" ? (
          <header className="pointer-events-auto flex items-start justify-between gap-2 bg-gradient-to-b from-black/90 to-transparent px-3 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-4">
            <button
              type="button"
              onClick={closeMap}
              className="inline-flex items-center gap-1.5 rounded border border-cyan-500/40 bg-black/80 px-3 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-300 shadow-lg sm:text-xs"
            >
              <X className="h-3.5 w-3.5" />
              CERRAR
            </button>
            <div className="flex flex-col items-end gap-2">
              <div className="flex items-center gap-2 rounded border border-cyan-500/30 bg-black/70 px-2 py-1.5">
                <MapPin className="h-3.5 w-3.5 text-cyan-400" />
                <span className="text-[10px] text-cyan-200 sm:text-xs">{gpsLabel}</span>
              </div>
            </div>
          </header>
        ) : null}

        <div className="pointer-events-auto space-y-2 px-3 sm:px-4">
          {ui.searchBar ? (
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
            </>
          ) : null}
          {ui.results && mapNav.placeOptions.length > 0 ? (
            <PlaceOptionsList
              query={mapNav.placeQuery}
              places={mapNav.placeOptions}
              onStart={(i) => void handleStartOption(i)}
              onCancel={handleCancelOptions}
              busy={navBusy}
            />
          ) : null}
        </div>

        <div className="flex-1" />

        {ui.routePreview && mapNav.route ? (
          <div className="pointer-events-auto px-3 pb-2 sm:px-4">
            <RoutePreviewPanel
              route={mapNav.route}
              onStart={beginNavigation}
              busy={navBusy}
            />
          </div>
        ) : null}

        <div className="pointer-events-auto border-t border-cyan-500/25 bg-black/85 px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md sm:px-4">
          <div className="mb-2 flex items-center gap-2">
            <Navigation className="h-4 w-4 text-cyan-400" />
            <p className="font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-widest text-cyan-300">
              MODO CONDUCIR · GPS + GUÍA
            </p>
          </div>

          {embedded ? (
            <p className="text-center text-xs leading-relaxed text-cyan-400">
              CED sigue escuchando en segundo plano. Di: &quot;busca Walmart&quot;,
              &quot;el primero&quot;, &quot;iniciar&quot;, &quot;detener&quot; o &quot;cerrar mapa&quot;.
            </p>
          ) : null}

          {geoError ? (
            <p className="mt-2 text-center text-xs text-amber-300">{geoError}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
