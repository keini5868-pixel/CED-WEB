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
  camera_stream_present?: boolean;
  client_action?: VoiceClientAction | null;
  tool_events?: Array<{
    id: number;
    type?: string;
    image_url?: string;
    prompt?: string;
  }>;
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

export async function postVoiceCameraStatus(
  active: boolean,
  streamPresent = active,
): Promise<void> {
  await proxyFetch("voice/camera-status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active, streamPresent }),
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

/** Registra imagen del chat para que la voz Retell pueda publicarla en Instagram. */
export async function postVoiceChatImage(payload: {
  image_url?: string;
  image_data?: string;
}): Promise<void> {
  if (!payload.image_url && !payload.image_data) return;
  await proxyFetch("voice/chat-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function postVoiceSessionEnd(): Promise<void> {
  await proxyFetch("voice/session-end", { method: "POST" });
}
