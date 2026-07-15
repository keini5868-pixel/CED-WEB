/**
 * Store singleton LIFE (Gmail/clima/aire/polen/calendar).
 * Varios componentes se suscriben; un solo pipeline de red (stale-while-revalidate).
 * Prioridad baja — no compite con el chat de texto.
 */

import {
  GOOGLE_CALENDAR_CONNECTED_EVENT,
  GOOGLE_GMAIL_CONNECTED_EVENT,
} from "@/components/voice/ConnectGoogleServices";
import {
  applyGoogleConnections,
  createLifeFallback,
  fetchHudConnections,
  fetchHudLife,
  type LifeDashboardSnapshot,
} from "../api/hud";
import { syncPendingGoogleProviderToken } from "../api/google";
import { createClient } from "../supabase/client";
import { readLifeCache, writeLifeCache } from "./lifeDataCache";

const CONNECTION_REFRESH_MS = 90 * 1000;
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
let connectionsBusy = false;
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

function mergeConnectionSlice(
  prev: LifeDashboardSnapshot,
  conn: Pick<LifeDashboardSnapshot, "calendar" | "gmail" | "updated_at">,
): LifeDashboardSnapshot {
  return {
    ...prev,
    updated_at: conn.updated_at || prev.updated_at,
    calendar: {
      ...prev.calendar,
      ...conn.calendar,
      title: "CALENDARIO",
      connected: prev.calendar.connected || conn.calendar.connected,
      today_events: conn.calendar.today_events ?? prev.calendar.today_events,
      week_events: conn.calendar.week_events ?? prev.calendar.week_events,
    },
    gmail: {
      ...prev.gmail,
      ...conn.gmail,
      title: "GMAIL",
      connected: prev.gmail.connected || conn.gmail.connected,
      items: conn.gmail.items ?? prev.gmail.items,
    },
  };
}

function mergeLifeSnapshot(
  prev: LifeDashboardSnapshot,
  snapshot: LifeDashboardSnapshot,
): LifeDashboardSnapshot {
  return {
    ...snapshot,
    calendar: {
      ...snapshot.calendar,
      connected: prev.calendar.connected || snapshot.calendar.connected,
      events: snapshot.calendar.connected
        ? snapshot.calendar.events
        : prev.calendar.events,
      today_events: snapshot.calendar.today_events?.length
        ? snapshot.calendar.today_events
        : prev.calendar.today_events,
      week_events: snapshot.calendar.week_events?.length
        ? snapshot.calendar.week_events
        : prev.calendar.week_events,
      error: snapshot.calendar.error ?? prev.calendar.error,
    },
    gmail: {
      ...snapshot.gmail,
      connected: prev.gmail.connected || snapshot.gmail.connected,
      messages: snapshot.gmail.connected
        ? snapshot.gmail.messages
        : prev.gmail.messages,
      unread_count: snapshot.gmail.connected
        ? snapshot.gmail.unread_count
        : prev.gmail.unread_count,
    },
  };
}

async function refreshConnections(showSpinner = false) {
  if (connectionsBusy) return;
  connectionsBusy = true;
  if (showSpinner) setState({ refreshingConnections: true });
  try {
    const conn = await fetchHudConnections({ priority: "low" });
    const next = mergeConnectionSlice(state.data, conn);
    setState({ data: next });
    persist(next);
  } catch {
    /* keep previous */
  } finally {
    connectionsBusy = false;
    if (showSpinner) setState({ refreshingConnections: false });
  }
}

async function refreshLifeContent() {
  if (weatherBusy) return;
  weatherBusy = true;
  setState({ loadingWeather: true });
  try {
    // Sin merge Google bloqueante: pintar clima/aire ya; OAuth en paralelo aparte.
    const snapshot = await fetchHudLife({
      mergeGoogleStatus: false,
      priority: "low",
    });
    const next = mergeLifeSnapshot(state.data, snapshot);
    setState({ data: next });
    persist(next);

    void applyGoogleConnections(next)
      .then((withGoogle) => {
        const merged = mergeLifeSnapshot(state.data, withGoogle);
        setState({ data: merged });
        persist(merged);
      })
      .catch(() => {
        /* ignore */
      });
  } catch {
    /* keep previous */
  } finally {
    weatherBusy = false;
    setState({ loadingWeather: false });
  }
}

function refreshConnectionsBg() {
  void refreshConnections(false);
}

function refreshWeatherBg() {
  void refreshLifeContent();
}

async function bootstrapNetwork() {
  try {
    const oauth = await syncPendingGoogleProviderToken();
    if (oauth.ok && oauth.type) {
      window.dispatchEvent(
        new Event(
          oauth.type === "calendar"
            ? GOOGLE_CALENDAR_CONNECTED_EVENT
            : GOOGLE_GMAIL_CONNECTED_EVENT,
        ),
      );
    }
  } catch {
    /* ignore */
  }

  // En paralelo — no await secuencial que atrase el clima tras Gmail.
  void refreshConnections(false);
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
      refreshConnectionsBg();
      if (bootstrapped) refreshWeatherBg();
    }
  });

  const connInterval = window.setInterval(
    refreshConnectionsBg,
    CONNECTION_REFRESH_MS,
  );
  const weatherInterval = window.setInterval(
    refreshWeatherBg,
    WEATHER_REFRESH_MS,
  );

  const onVisible = () => {
    if (document.visibilityState === "visible") refreshConnectionsBg();
  };
  const onFocus = () => {
    refreshConnectionsBg();
  };
  const onGoogleConnected = () => {
    void refreshConnections(false).then(() => refreshWeatherBg());
  };

  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("focus", onFocus);
  window.addEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onGoogleConnected);
  window.addEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onGoogleConnected);

  teardown = () => {
    window.clearTimeout(bootTimer);
    subscription.unsubscribe();
    window.clearInterval(connInterval);
    window.clearInterval(weatherInterval);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("focus", onFocus);
    window.removeEventListener(
      GOOGLE_CALENDAR_CONNECTED_EVENT,
      onGoogleConnected,
    );
    window.removeEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onGoogleConnected);
    started = false;
    bootstrapped = false;
    teardown = null;
  };
}

/** Manual ↻ — espera conexiones; clima en background. */
export async function refreshLifeStoreManual(): Promise<void> {
  ensureLifeStoreStarted();
  await refreshConnections(true);
  refreshWeatherBg();
}

export function refreshLifeStoreConnections(): void {
  ensureLifeStoreStarted();
  refreshConnectionsBg();
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
  connectionsBusy = false;
  bootstrapped = false;
}
