import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type WhatsAppStatus = {
  connected: boolean;
  display_phone?: string | null;
  display_phone?: string | null;
  verified_name?: string | null;
  verified_name?: string | null;
  phone_number_id?: string | null;
  status?: string | null;
  automation_goal?: string;
  automation_cta_url?: string;
  automation_cta_label?: string;
};

export type WhatsAppConnectConfig = {
  app_id: string;
  app_id?: string;
  config_id: string | null;
  config_id?: string | null;
  api_version: string;
  api_version?: string;
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

export async function saveWhatsAppAutomation(body: {
  goal: string;
  cta_url: string;
  cta_label: string;
}): Promise<{ error?: string }> {
  const res = await proxyFetch("whatsapp/automation", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await parseApiJson<{ detail?: string }>(res);
  if (!res.ok) {
    return { error: data.detail || "No se pudo guardar el objetivo." };
  }
  return {};
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

export async function sendWhatsAppText(to: string, body: string): Promise<{ error?: string }> {
  const res = await proxyFetch("whatsapp/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, body }),
  });
  const data = await parseApiJson<{ detail?: string }>(res);
  if (!res.ok) return { error: data.detail || "No se pudo enviar." };
  return {};
}

export type WhatsAppTemplate = {
  name?: string;
  status?: string;
  language?: string;
  category?: string;
};

export async function fetchWhatsAppTemplates(): Promise<WhatsAppTemplate[]> {
  const res = await proxyFetch("whatsapp/templates");
  if (!res.ok) return [];
  const data = (await res.json()) as { templates?: WhatsAppTemplate[] };
  return data.templates ?? [];
}

export async function createWhatsAppTemplate(body: {
  name: string;
  language: string;
  body: string;
  category: string;
}): Promise<{ error?: string }> {
  const res = await proxyFetch("whatsapp/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await parseApiJson<{ detail?: string }>(res);
  if (!res.ok) return { error: data.detail || "No se pudo crear la plantilla." };
  return {};
}

export async function sendWhatsAppTemplate(body: {
  to: string;
  name: string;
  language: string;
  body_params?: string[];
}): Promise<{ error?: string }> {
  const res = await proxyFetch("whatsapp/templates/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await parseApiJson<{ detail?: string }>(res);
  if (!res.ok) return { error: data.detail || "No se pudo enviar la plantilla." };
  return {};
}
export async function fetchWhatsAppMessages(): Promise<WhatsAppMessage[]> {
  const res = await proxyFetch("whatsapp/messages");
  if (!res.ok) return [];
  const data = (await res.json()) as { messages?: WhatsAppMessage[] };
  return data.messages ?? [];
}
