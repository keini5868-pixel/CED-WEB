export type RetellTransportKind = "livekit" | "gateway";

export type RetellIceServer = {
  urls: string | string[];
  username?: string;
  credential?: string;
};

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  const payload = parts[1];
  if (!payload) return null;
  try {
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const json = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    const data = JSON.parse(json) as unknown;
    return data && typeof data === "object" ? (data as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Tokens de gateway y LiveKit se parecen; adivinar mal provoca "Error starting call". */
export function inferRetellTransport(opts: {
  transport?: string | null;
  accessToken: string;
  iceServers?: RetellIceServer[] | null;
}): RetellTransportKind {
  const hinted = String(opts.transport || "").trim().toLowerCase();
  if (hinted === "gateway" || hinted === "livekit") return hinted;
  if (Array.isArray(opts.iceServers) && opts.iceServers.length > 0) return "gateway";
  const payload = decodeJwtPayload(opts.accessToken);
  const inst = payload?.inst;
  if (typeof inst === "string" && inst.trim()) return "gateway";
  const video = payload?.video;
  if (video && typeof video === "object" && !("room" in video && (video as { room?: unknown }).room)) {
    return "gateway";
  }
  return "livekit";
}

export function mapRetellClientError(message: string): string {
  const low = message.trim().toLowerCase();
  if (!low || low.includes("error starting call") || low.includes("starting call")) {
    return "No pude conectar la llamada de voz. Permita el micrófono e intente de nuevo.";
  }
  return message;
}
