import type { VoiceSessionPreferences } from "@ced/types";

/** Preset formal-ejecutivo estilo asistente premium (Jarvis). */
export const JARVIS_VOICE_PRESET: VoiceSessionPreferences = {
  language: "es",
  responseSpeed: "balanced",
  voiceName: "echo",
  palette: "cyan",
  voicePace: 38,
  voiceWarmth: 42,
  voiceEnergy: 38,
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
