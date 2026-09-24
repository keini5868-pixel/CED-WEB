import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";
import type { NavRoute } from "@/lib/api/navigation";

const proxyFetch = (path: string, init?: RequestInit) =>
  fetch(cedApiPath(path), { credentials: "same-origin", ...init });

export type VoiceClientAction = {
  id: number;
  action: string;
  payload: Record<string, unknown>;
};

export type VoiceToolEvent = {
  id: number;
  type?: string;
  module?: string;
  image_url?: string;
  prompt?: string;
  title?: string;
  file_id?: string;
  text?: string;
  query?: string;
  places?: unknown[];
  action?: string;
  destination?: string;
  index?: number;
  route?: NavRoute;
  video_id?: string;
  channel_title?: string;
  thumbnail_url?: string;
  resource?: string;
  message?: string;
};

export type VoiceLiveTranscript = {
  seq?: number;
  role?: "user" | "model" | string;
  text?: string;
  stream_key?: string;
  partial?: boolean;
};

export type VoiceTranscriptTurn = {
  id?: string;
  role?: string;
  content?: string;
  created_at?: string;
};

export type VoiceClientState = {
  ok: boolean;
  camera_active?: boolean;
  camera_stream_present?: boolean;
  client_action?: VoiceClientAction | null;
  tool_events?: VoiceToolEvent[];
  live_transcript?: VoiceLiveTranscript | null;
  conversation_id?: string | null;
  transcript_turns?: VoiceTranscriptTurn[];
};

export async function fetchVoiceClientState(
  consume = false,
  opts?: { transcript?: boolean },
): Promise<VoiceClientState> {
  const qs = new URLSearchParams();
  if (consume) qs.set("consume", "true");
  if (opts?.transcript) qs.set("transcript", "true");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await proxyFetch(`voice/client-state${suffix}`);
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

/** Pre-autorización de cámara al iniciar sesión (gesto de usuario). */
export async function postVoiceCameraPermission(granted: boolean): Promise<void> {
  await proxyFetch("voice/camera-status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      active: false,
      streamPresent: false,
      permissionGranted: granted,
    }),
  });
}

export async function postVoiceVisionResult(
  requestId: number,
  summary: string,
): Promise<void> {
  const res = await proxyFetch("voice/vision-result", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, summary }),
  });
  if (!res.ok) {
    console.warn("[VISION] vision-result failed status=%s request_id=%s", res.status, requestId);
  }
}

export async function ackVoiceClientAction(actionId: number): Promise<void> {
  await proxyFetch("voice/ack-action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_id: actionId }),
  });
}

/** Registra imagen del chat para que la voz Retell pueda publicarla/analizarla. */
export type VoiceChatImageResponse = {
  ok: boolean;
  image_url?: string;
  public_url?: string;
  size_bytes?: number;
  filename?: string;
  meta_draft_ready?: boolean;
  draft_id?: string;
  meta_spoken?: string;
  caption_preview?: string;
  reason?: string;
  detail?: string | Array<{ type?: string; msg?: string }>;
};

export async function postVoiceChatImage(payload: {
  image_url?: string;
  image_data?: string;
  filename?: string;
}): Promise<VoiceChatImageResponse> {
  if (!payload.image_url && !payload.image_data) {
    throw new Error("Imagen vacía.");
  }
  const res = await proxyFetch("voice/chat-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = (await res.json().catch(() => ({}))) as VoiceChatImageResponse;
  if (!res.ok || data.ok === false) {
    const errorMessage = (() => {
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail) && data.detail.length > 0) {
        const first = data.detail[0] as { type?: string; msg?: string };
        if (first.type === "string_too_long") {
          return "Imagen demasiado grande. Intenta con una más pequeña.";
        }
        return first.msg || "Error de validación al subir imagen";
      }
      return data.reason || "Error al subir imagen";
    })();
    throw new Error(errorMessage);
  }
  return data;
}

export async function deleteVoiceChatImage(): Promise<void> {
  await proxyFetch("voice/chat-image", { method: "DELETE" });
}

export async function postVoiceSessionEnd(): Promise<void> {
  await proxyFetch("voice/session-end", { method: "POST" });
}
