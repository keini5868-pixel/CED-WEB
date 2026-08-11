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

/** Piloto Retell LLM nativo — activar con ?voicePilot=native o NEXT_PUBLIC_RETELL_NATIVE_PILOT=true */
export function isRetellNativePilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const pilot = params.get("voicePilot")?.trim().toLowerCase();
    if (pilot === "native") return true;
    if (pilot === "prod" || pilot === "production") return false;
  }
  return process.env.NEXT_PUBLIC_RETELL_NATIVE_PILOT === "true";
}
