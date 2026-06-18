import { parseApiJson } from "@/lib/api/http";
import { proxyFetch } from "@/lib/api/ced-proxy";

export type RetellRegisterCallResponse =
  | {
      ok: true;
      access_token: string;
      call_id?: string | null;
      agent_id?: string;
    }
  | { ok: false; error?: string; detail?: string };

export async function warmupRetellVoiceApi(): Promise<void> {
  try {
    await proxyFetch("retell/warmup", { method: "GET" });
  } catch {
    /* ignore — best effort */
  }
}

export async function registerRetellCall(): Promise<RetellRegisterCallResponse> {
  let response: Response;
  try {
    response = await proxyFetch("retell/register-call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  } catch {
    return { ok: false, error: "No se pudo contactar la API de voz." };
  }

  const data = await parseApiJson<RetellRegisterCallResponse & { detail?: string }>(
    response,
  ).catch(() => ({ ok: false as const, error: `Error ${response.status}` }));

  if (!response.ok) {
    const errData = data as { error?: string; detail?: string };
    return {
      ok: false,
      error: errData.detail || errData.error || `Error ${response.status}`,
    };
  }

  if (!("access_token" in data) || !data.access_token) {
    return { ok: false, error: "La API no devolvió access_token de Retell." };
  }

  return {
    ok: true,
    access_token: data.access_token,
    call_id: data.call_id,
    agent_id: data.agent_id,
  };
}

export type RetellConfigResponse = {
  provider: string;
  agentConfigured: boolean;
  voiceId?: string;
};

export async function fetchRetellConfig(): Promise<RetellConfigResponse | null> {
  try {
    const response = await proxyFetch("retell/config", { method: "GET" });
    if (!response.ok) return null;
    return await parseApiJson<RetellConfigResponse>(response);
  } catch {
    return null;
  }
}
