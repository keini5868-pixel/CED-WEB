import { authHeaders } from "@/lib/api/auth";
import { proxyFetch } from "@/lib/api/ced-proxy";
import {
  AUTOMATION_PILOT_HEADER,
  AUTOMATION_PILOT_HEADER_VALUE,
} from "@/lib/pilot/automationModule";

function pilotHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    "Content-Type": "application/json",
    [AUTOMATION_PILOT_HEADER]: AUTOMATION_PILOT_HEADER_VALUE,
    ...(extra || {}),
  };
}

export type AutomationCard = {
  card_key: string | null;
  name: string;
  description: string;
  channel: string;
  trigger_type: string;
  status: string;
  id?: string;
  last_triggered_at?: string | null;
  configured: boolean;
};

export type AutomationStatus = {
  ok: boolean;
  enabled: boolean;
  ig_fb_live: boolean;
  dry_run: boolean;
  active_count: number;
  active_cap: number;
  narrative: string;
  stats: Record<string, number>;
  meta_scopes_note?: string;
};

async function parseJson<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail || res.statusText;
    throw new Error(String(detail));
  }
  return data as T;
}

export async function fetchAutomationStatus(): Promise<AutomationStatus> {
  const res = await proxyFetch("/v1/automation-pilot/status", {
    headers: { ...authHeaders(), ...pilotHeaders() },
  });
  return parseJson(res);
}

export async function fetchAutomationCards(): Promise<AutomationCard[]> {
  const res = await proxyFetch("/v1/automation-pilot/cards", {
    headers: { ...authHeaders(), ...pilotHeaders() },
  });
  const data = await parseJson<{ cards: AutomationCard[] }>(res);
  return data.cards || [];
}

export async function ensureAutomationCard(
  cardKey: string,
  activate = false,
): Promise<{ ok: boolean; automation?: { id: string; status: string }; error?: string }> {
  const res = await proxyFetch("/v1/automation-pilot/cards/ensure", {
    method: "POST",
    headers: { ...authHeaders(), ...pilotHeaders() },
    body: JSON.stringify({ card_key: cardKey, activate }),
  });
  return parseJson(res);
}

export async function setAutomationStatus(
  automationId: string,
  status: "active" | "paused",
): Promise<{ ok: boolean; error?: string }> {
  const res = await proxyFetch(`/v1/automation-pilot/automations/${automationId}/status`, {
    method: "POST",
    headers: { ...authHeaders(), ...pilotHeaders() },
    body: JSON.stringify({ status }),
  });
  return parseJson(res);
}

export async function previewAutomationSpeech(text: string): Promise<{
  ok: boolean;
  preview?: Record<string, unknown>;
  error?: string;
}> {
  const res = await proxyFetch("/v1/automation-pilot/preview", {
    method: "POST",
    headers: { ...authHeaders(), ...pilotHeaders() },
    body: JSON.stringify({ text }),
  });
  return parseJson(res);
}

export async function confirmAutomationPreview(
  preview: Record<string, unknown>,
  activate: boolean,
): Promise<{ ok: boolean; message?: string; error?: string }> {
  const res = await proxyFetch("/v1/automation-pilot/confirm", {
    method: "POST",
    headers: { ...authHeaders(), ...pilotHeaders() },
    body: JSON.stringify({ preview, activate }),
  });
  return parseJson(res);
}
