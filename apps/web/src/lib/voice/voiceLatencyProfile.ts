import type { VoiceSessionPreferences } from "@ced/types";

export type VoiceLatencyProfile = {
  silenceMs: number;
  minSpeechMs: number;
  speechRms: number;
  chunkMs: number;
  temperature: number;
  maxOutputTokens: number;
  activityCooldownMs: number;
};

/** Perfiles calibrados para Gemini Live (server VAD + stream continuo). */
export function profileForResponseSpeed(
  speed: VoiceSessionPreferences["responseSpeed"],
): VoiceLatencyProfile {
  switch (speed) {
    case "fast":
      return {
        silenceMs: 520,
        minSpeechMs: 180,
        speechRms: 0.016,
        chunkMs: 20,
        temperature: 0.42,
        maxOutputTokens: 1024,
        activityCooldownMs: 80,
      };
    case "thoughtful":
      return {
        silenceMs: 680,
        minSpeechMs: 280,
        speechRms: 0.017,
        chunkMs: 30,
        temperature: 0.6,
        maxOutputTokens: 1536,
        activityCooldownMs: 400,
      };
    default:
      return {
        silenceMs: 480,
        minSpeechMs: 160,
        speechRms: 0.016,
        chunkMs: 20,
        temperature: 0.5,
        maxOutputTokens: 896,
        activityCooldownMs: 180,
      };
  }
}
