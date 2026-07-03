import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type NavLatLng = { lat: number; lng: number };

export type NavStep = {
  instruction: string;
  distance_m: number;
  duration_s: number;
  maneuver: string;
  start: NavLatLng;
  end: NavLatLng;
};

export type NavRoute = {
  destination: { label: string; lat: number; lng: number };
  distance_text: string;
  duration_text: string;
  distance_m: number;
  duration_s: number;
  path: NavLatLng[];
  steps: NavStep[];
};

export type NavClientAction = {
  action: string;
  payload: Record<string, unknown>;
  id: number;
};

export type NavPlaceOption = {
  name: string;
  address: string;
  lat: number;
  lng: number;
  place_id?: string;
  distance_m?: number;
  distance_text?: string;
};

export type NavigationState = {
  ok?: boolean;
  location?: Record<string, unknown> | null;
  route?: NavRoute | null;
  place_options?: NavPlaceOption[] | null;
  place_query?: string;
  client_action?: NavClientAction | null;
  navigating?: boolean;
};

export type NavigationMapState = {
  route: NavRoute | null;
  destinationPin: { lat: number; lng: number; label: string } | null;
  placeOptions: NavPlaceOption[];
  placeQuery: string;
};

type RouteApiPayload = {
  ok?: boolean;
  error?: string;
  route?: NavRoute;
  destination?: NavRoute["destination"];
  path?: NavLatLng[];
  steps?: NavStep[];
  distance_text?: string;
  duration_text?: string;
  distance_m?: number;
  duration_s?: number;
};

function buildPathFromSteps(steps: NavStep[] | undefined): NavLatLng[] {
  if (!steps?.length) return [];
  const pts: NavLatLng[] = [];
  for (const step of steps) {
    if (step.start) pts.push(step.start);
  }
  const last = steps[steps.length - 1];
  if (last?.end) pts.push(last.end);
  return pts;
}

function parseRouteResponse(data: RouteApiPayload): {
  ok: boolean;
  route?: NavRoute;
  error?: string;
} {
  if (data.ok === false) {
    return { ok: false, error: data.error || "No pude calcular la ruta." };
  }
  if (data.route?.destination) {
    const path =
      data.route.path?.length > 1
        ? data.route.path
        : buildPathFromSteps(data.route.steps);
    return {
      ok: true,
      route: { ...data.route, path: path.length > 1 ? path : data.route.path ?? [] },
    };
  }
  if (data.destination) {
    const steps = data.steps || [];
    const path =
      Array.isArray(data.path) && data.path.length > 1
        ? data.path
        : buildPathFromSteps(steps);
    return {
      ok: true,
      route: {
        destination: data.destination,
        path,
        steps,
        distance_text: data.distance_text || "",
        duration_text: data.duration_text || "",
        distance_m: data.distance_m || 0,
        duration_s: data.duration_s || 0,
      },
    };
  }
  return { ok: false, error: data.error || "Respuesta de ruta inválida." };
}

export async function fetchNavigationState(consume = false): Promise<NavigationState> {
  const qs = consume ? "?consume=true" : "";
  const res = await proxyFetch(`navigation/state${qs}`);
  if (res.status === 401 || res.status === 403) {
    return { ok: false };
  }
  if (!res.ok) {
    return { ok: false };
  }
  return parseApiJson<NavigationState>(res);
}

export async function postNavigationLocation(body: {
  lat: number;
  lng: number;
  heading?: number | null;
  speed?: number | null;
  accuracy?: number | null;
}): Promise<void> {
  await proxyFetch("navigation/location", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function ackNavigationAction(actionId: number): Promise<void> {
  await proxyFetch("navigation/ack-action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_id: actionId }),
  });
}

export async function geocodeDestination(query: string): Promise<{
  ok: boolean;
  formatted_address?: string;
  lat?: number;
  lng?: number;
  error?: string;
}> {
  const res = await proxyFetch("navigation/geocode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  return parseApiJson(res);
}

export async function computeNavigationRoute(destination: string): Promise<{
  ok: boolean;
  route?: NavRoute;
  error?: string;
}> {
  const res = await proxyFetch("navigation/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ destination }),
  });
  const data = await parseApiJson<RouteApiPayload>(res);
  return parseRouteResponse(data);
}

export async function computeNavigationRouteTo(body: {
  lat: number;
  lng: number;
  label: string;
}): Promise<{
  ok: boolean;
  route?: NavRoute;
  error?: string;
}> {
  const res = await proxyFetch("navigation/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dest_lat: body.lat,
      dest_lng: body.lng,
      dest_label: body.label,
    }),
  });
  const data = await parseApiJson<RouteApiPayload>(res);
  return parseRouteResponse(data);
}

export async function cancelNavigation(): Promise<void> {
  await proxyFetch("navigation/cancel", { method: "POST" });
}

export async function searchNearbyPlaces(query: string): Promise<{
  ok: boolean;
  query?: string;
  places?: NavPlaceOption[];
  error?: string;
}> {
  const res = await proxyFetch("navigation/nearby", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  return parseApiJson(res);
}

export async function suggestNavigationPlaces(query: string): Promise<{
  ok: boolean;
  suggestions?: Array<{
    label: string;
    address?: string;
    lat: number;
    lng: number;
  }>;
}> {
  const qs = encodeURIComponent(query.trim());
  const res = await proxyFetch(`navigation/suggest?q=${qs}`);
  if (res.status === 401 || res.status === 403) {
    return { ok: false, suggestions: [] };
  }
  if (!res.ok) {
    return { ok: false, suggestions: [] };
  }
  return parseApiJson(res);
}

export async function startNavigationOption(index: number): Promise<{
  ok: boolean;
  route?: NavRoute;
  error?: string;
}> {
  const res = await proxyFetch("navigation/start-option", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  const data = await parseApiJson<RouteApiPayload>(res);
  return parseRouteResponse(data);
}
