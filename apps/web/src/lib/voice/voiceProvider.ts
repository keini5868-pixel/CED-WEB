export type VoiceProvider = "retell" | "openai";

export function getEnvVoiceProvider(): VoiceProvider {
  const raw = (process.env.NEXT_PUBLIC_VOICE_PROVIDER || "retell").trim().toLowerCase();
  return raw === "openai" ? "openai" : "retell";
}

/** @deprecated prefer resolveVoiceProvider with plan/stack */
export function getVoiceProvider(): VoiceProvider {
  return getEnvVoiceProvider();
}

export type VoiceRouteInput = {
  planId?: string | null;
  voiceStack?: string | null;
  voiceTransport?: string | null;
};

/**
 * Todos los planes → Retell Jarvis (stack OpenAI Realtime / Cierre $20 retirado).
 * Solo fuerza openai si NEXT_PUBLIC_VOICE_PROVIDER=openai.
 */
export function resolveVoiceProvider(route?: VoiceRouteInput | null): VoiceProvider {
  void route;
  return getEnvVoiceProvider();
}

export function isRetellVoice(route?: VoiceRouteInput | null): boolean {
  return resolveVoiceProvider(route) === "retell";
}

/**
 * Retell LLM nativo (prompt + tools en Retell) — default en producción.
 * Custom LLM (WebSocket API + Claude) solo con ?voicePilot=custom o
 * NEXT_PUBLIC_RETELL_NATIVE_PILOT=false.
 */
export function isRetellNativePilot(): boolean {
  const envDefault = (process.env.NEXT_PUBLIC_RETELL_NATIVE_PILOT || "true")
    .trim()
    .toLowerCase();
  if (typeof window === "undefined") {
    return envDefault !== "false";
  }
  const pilot = new URLSearchParams(window.location.search)
    .get("voicePilot")
    ?.trim()
    .toLowerCase();
  if (pilot === "custom") {
    return false;
  }
  if (pilot === "native") {
    return true;
  }
  return envDefault !== "false";
}
