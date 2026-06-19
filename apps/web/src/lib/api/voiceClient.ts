import { proxyGet, proxyPost } from "@/lib/api/proxy";

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
  const q = consume ? "?consume=true" : "";
  return proxyGet<VoiceClientState>(`voice/client-state${q}`);
}

export async function postVoiceCameraStatus(active: boolean): Promise<void> {
  await proxyPost("voice/camera-status", { active });
}

export async function postVoiceVisionResult(
  requestId: number,
  summary: string,
): Promise<void> {
  await proxyPost("voice/vision-result", { request_id: requestId, summary });
}

export async function ackVoiceClientAction(actionId: number): Promise<void> {
  await proxyPost("voice/ack-action", { action_id: actionId });
}
