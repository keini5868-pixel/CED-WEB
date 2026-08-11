export type VoiceProvider = "retell" | "openai";

/** Planes FitLine / Cierre — sin Jarvis (Retell). */
const GEMINI_STACK_PLANS = new Set(["cierre"]);

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
 * FitLine/Cierre → openai (voz conversacional CED, sin Jarvis).
 * Planes premium CED → retell (Jarvis), salvo que el env fuerce openai global.
 */
export function resolveVoiceProvider(route?: VoiceRouteInput | null): VoiceProvider {
  const plan = (route?.planId || "").trim().toLowerCase();
  const stack = (route?.voiceStack || "").trim().toLowerCase();
  const transport = (route?.voiceTransport || "").trim().toLowerCase();
  if (
    transport === "openai" ||
    stack === "gemini" ||
    GEMINI_STACK_PLANS.has(plan)
  ) {
    return "openai";
  }
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
