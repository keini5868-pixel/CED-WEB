export type VoiceProvider = "retell" | "openai";

export function getVoiceProvider(): VoiceProvider {
  const raw = (process.env.NEXT_PUBLIC_VOICE_PROVIDER || "retell").trim().toLowerCase();
  return raw === "openai" ? "openai" : "retell";
}

export function isRetellVoice(): boolean {
  return getVoiceProvider() === "retell";
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
