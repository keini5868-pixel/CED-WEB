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

export type NavigationState = {
  ok?: boolean;
  location?: Record<string, unknown> | null;
  route?: NavRoute | null;
  client_action?: NavClientAction | null;
  navigating?: boolean;
};

export type NavigationMapState = {
  route: NavRoute | null;
  destinationPin: { lat: number; lng: number; label: string } | null;
};

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
  return parseApiJson(res);
}

export async function cancelNavigation(): Promise<void> {
  await proxyFetch("navigation/cancel", { method: "POST" });
}
