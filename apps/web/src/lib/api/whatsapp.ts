import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type WhatsAppStatus = {
  connected: boolean;
  display_phone?: string | null;
  verified_name?: string | null;
  phone_number_id?: string | null;
  status?: string | null;
};

export type WhatsAppConnectConfig = {
  app_id: string;
  config_id: string | null;
  api_version: string;
  webhook_url: string;
  verify_token_configured: boolean;
};

export type WhatsAppFlow = {
  id: string;
  name: string;
  trigger_type: string;
  keywords: string;
  reply_text: string;
  enabled: boolean;
  priority: number;
};

export type WhatsAppMessage = {
  id: string;
  direction: string;
  wa_from?: string | null;
  wa_to?: string | null;
  body?: string | null;
  created_at?: string;
};

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export async function fetchWhatsAppStatus(): Promise<WhatsAppStatus | null> {
  try {
    const res = await proxyFetch("whatsapp/status");
    if (!res.ok) return null;
    return (await res.json()) as WhatsAppStatus;
  } catch {
    return null;
  }
}

export async function fetchWhatsAppConnectConfig(): Promise<
  WhatsAppConnectConfig | { error: string }
> {
  const res = await proxyFetch("whatsapp/connect/config");
  const data = await parseApiJson<WhatsAppConnectConfig & { detail?: string }>(res);
  if (!res.ok) {
    return { error: data.detail || "No se pudo cargar la conexión WhatsApp." };
  }
  return data;
}

export async function connectWhatsApp(payload: {
  code?: string;
  waba_id?: string;
  phone_number_id?: string;
}): Promise<{ ok?: boolean; error?: string; display_phone?: string | null }> {
  const res = await proxyFetch("whatsapp/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseApiJson<{
    ok?: boolean;
    detail?: string;
    display_phone?: string | null;
  }>(res);
  if (!res.ok) {
    return { error: data.detail || "No se pudo conectar WhatsApp." };
  }
  return { ok: true, display_phone: data.display_phone };
}

export async function disconnectWhatsApp(): Promise<boolean> {
  const res = await proxyFetch("whatsapp/connect", { method: "DELETE" });
  return res.ok;
}

export async function fetchWhatsAppFlows(): Promise<WhatsAppFlow[]> {
  const res = await proxyFetch("whatsapp/flows");
  if (!res.ok) return [];
  const data = (await res.json()) as { flows?: WhatsAppFlow[] };
  return data.flows ?? [];
}

export async function createWhatsAppFlow(body: {
  name: string;
  trigger_type: string;
  keywords: string;
  reply_text: string;
  enabled: boolean;
  priority: number;
}): Promise<{ flow?: WhatsAppFlow; error?: string }> {
  const res = await proxyFetch("whatsapp/flows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await parseApiJson<{ flow?: WhatsAppFlow; detail?: string }>(res);
  if (!res.ok) return { error: data.detail || "No se pudo crear el flujo." };
  return { flow: data.flow };
}

export async function patchWhatsAppFlow(
  id: string,
  patch: Partial<{
    name: string;
    trigger_type: string;
    keywords: string;
    reply_text: string;
    enabled: boolean;
    priority: number;
  }>,
): Promise<{ error?: string }> {
  const res = await proxyFetch(`whatsapp/flows/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const data = await parseApiJson<{ detail?: string }>(res);
    return { error: data.detail || "No se pudo actualizar." };
  }
  return {};
}

export async function deleteWhatsAppFlow(id: string): Promise<boolean> {
  const res = await proxyFetch(`whatsapp/flows/${id}`, { method: "DELETE" });
  return res.ok;
}

export async function fetchWhatsAppMessages(): Promise<WhatsAppMessage[]> {
  const res = await proxyFetch("whatsapp/messages");
  if (!res.ok) return [];
  const data = (await res.json()) as { messages?: WhatsAppMessage[] };
  return data.messages ?? [];
}
