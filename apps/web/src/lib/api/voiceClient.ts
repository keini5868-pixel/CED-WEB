import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type VoiceClientAction = {
  id: number;
  action: string;
  payload: Record<string, unknown>;
};

export type VoiceClientState = {
  ok: boolean;
  camera_active?: boolean;
  client_action?: VoiceClientAction | null;
};

export async function fetchVoiceClientState(consume = false): Promise<VoiceClientState> {
  const qs = consume ? "?consume=true" : "";
  const res = await proxyFetch(`voice/client-state${qs}`);
  if (res.status === 401 || res.status === 403) {
    return { ok: false };
  }
  if (!res.ok) {
    return { ok: false };
  }
  return parseApiJson<VoiceClientState>(res);
}

export async function postVoiceCameraStatus(active: boolean): Promise<void> {
  await proxyFetch("voice/camera-status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
}

export async function postVoiceVisionResult(
  requestId: number,
  summary: string,
): Promise<void> {
  await proxyFetch("voice/vision-result", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, summary }),
  });
}

export async function ackVoiceClientAction(actionId: number): Promise<void> {
  await proxyFetch("voice/ack-action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_id: actionId }),
  });
}
