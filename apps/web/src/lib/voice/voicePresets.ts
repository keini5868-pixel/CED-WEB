import type { VoiceSessionPreferences } from "@ced/types";

/** Preset Jarvis: voz masculina pausada, formal, articulación clara. */
export const JARVIS_VOICE_PRESET: VoiceSessionPreferences = {
  language: "es",
  responseSpeed: "thoughtful",
  voiceName: "echo",
  palette: "cyan",
  voicePace: 22,
  voiceWarmth: 30,
  voiceEnergy: 28,
  voiceProfile: "jarvis",
};

/** Preset conversacional equilibrado (anterior). */
export const STANDARD_VOICE_PRESET: VoiceSessionPreferences = {
  language: "es",
  responseSpeed: "fast",
  voiceName: "alloy",
  palette: "cyan",
  voicePace: 50,
  voiceWarmth: 55,
  voiceEnergy: 50,
  voiceProfile: "standard",
};

export function isJarvisPreset(prefs: VoiceSessionPreferences): boolean {
  return prefs.voiceProfile === "jarvis";
}
