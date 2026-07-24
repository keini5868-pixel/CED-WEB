/**
 * Store singleton LIFE (clima/aire/polen).
 * Varios componentes se suscriben; un solo pipeline de red (stale-while-revalidate).
 * Prioridad baja — no compite con el chat de texto.
 */

import {
  createLifeFallback,
  fetchHudLife,
  type LifeDashboardSnapshot,
} from "../api/hud";
import { createClient } from "../supabase/client";
import { readLifeCache, writeLifeCache } from "./lifeDataCache";

const WEATHER_REFRESH_MS = 15 * 60 * 1000;
/** Deja que el primer paint / apertura de chat robe bandwidth. */
const BOOT_NETWORK_DEFER_MS = 120;

type Listener = () => void;

type StoreState = {
  data: LifeDashboardSnapshot;
  refreshingConnections: boolean;
  loadingWeather: boolean;
};

let state: StoreState = {
  data: createLifeFallback(),
  refreshingConnections: false,
  loadingWeather: false,
};

const listeners = new Set<Listener>();
let started = false;
let weatherBusy = false;
let bootstrapped = false;
let teardown: (() => void) | null = null;

function emit() {
  for (const listener of listeners) listener();
}

function setState(patch: Partial<StoreState>) {
  state = { ...state, ...patch };
  emit();
}

function persist(data: LifeDashboardSnapshot) {
  writeLifeCache(data);
}

async function refreshLifeContent() {
  if (weatherBusy) return;
  weatherBusy = true;
  setState({ loadingWeather: true });
  try {
    const snapshot = await fetchHudLife({ priority: "low" });
    setState({ data: snapshot });
    persist(snapshot);
  } catch {
    /* keep previous */
  } finally {
    weatherBusy = false;
    setState({ loadingWeather: false });
  }
}

function refreshWeatherBg() {
  void refreshLifeContent();
}

async function bootstrapNetwork() {
  void refreshLifeContent();
  bootstrapped = true;
}

export function getLifeStoreSnapshot(): StoreState {
  return state;
}

export function getLifeStoreServerSnapshot(): StoreState {
  return {
    data: createLifeFallback(),
    refreshingConnections: false,
    loadingWeather: false,
  };
}

export function subscribeLifeStore(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Arranca listeners + refresh una sola vez (idempotente). */
export function ensureLifeStoreStarted(): void {
  if (typeof window === "undefined" || started) return;
  started = true;

  const cached = readLifeCache() ?? createLifeFallback();
  state = {
    data: cached,
    refreshingConnections: false,
    loadingWeather: false,
  };
  emit();

  const bootTimer = window.setTimeout(() => {
    void bootstrapNetwork();
  }, BOOT_NETWORK_DEFER_MS);

  const supabase = createClient();
  const {
    data: { subscription },
  } = supabase.auth.onAuthStateChange((event, session) => {
    if (
      session?.access_token &&
      (event === "SIGNED_IN" ||
        event === "TOKEN_REFRESHED" ||
        event === "INITIAL_SESSION")
    ) {
      if (bootstrapped) refreshWeatherBg();
    }
  });

  const weatherInterval = window.setInterval(
    refreshWeatherBg,
    WEATHER_REFRESH_MS,
  );

  const onVisible = () => {
    if (document.visibilityState === "visible") refreshWeatherBg();
  };
  const onFocus = () => {
    refreshWeatherBg();
  };

  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("focus", onFocus);

  teardown = () => {
    window.clearTimeout(bootTimer);
    subscription.unsubscribe();
    window.clearInterval(weatherInterval);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("focus", onFocus);
    started = false;
    bootstrapped = false;
    teardown = null;
  };
}

/** Manual ↻ — refresca clima. */
export async function refreshLifeStoreManual(): Promise<void> {
  ensureLifeStoreStarted();
  await refreshLifeContent();
}

export function refreshLifeStoreConnections(): void {
  ensureLifeStoreStarted();
  refreshWeatherBg();
}

/** Solo tests / HMR extremo. */
export function __resetLifeStoreForTests(): void {
  teardown?.();
  state = {
    data: createLifeFallback(),
    refreshingConnections: false,
    loadingWeather: false,
  };
  weatherBusy = false;
  bootstrapped = false;
}
