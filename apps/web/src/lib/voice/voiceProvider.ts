export type VoiceProvider = "retell" | "openai";

export function getVoiceProvider(): VoiceProvider {
  const raw = (process.env.NEXT_PUBLIC_VOICE_PROVIDER || "retell").trim().toLowerCase();
  return raw === "openai" ? "openai" : "retell";
}

export function isRetellVoice(): boolean {
  return getVoiceProvider() === "retell";
}
