import type { LiveConnectConfig } from "@google/genai";
import {
  ActivityHandling,
  EndSensitivity,
  Modality,
  StartSensitivity,
} from "@google/genai";

import type { VoiceSessionPreferences } from "@ced/types";

import { sessionLanguageInstruction } from "@/lib/voice/transcriptAccumulator";
import { LIVE_FUNCTION_DECLARATIONS } from "@/lib/voice/liveTools";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import { profileForResponseSpeed } from "@/lib/voice/voiceLatencyProfile";

export function buildLiveConfig(params: {
  systemInstruction: string;
  voiceName: string;
  language: VoiceSessionPreferences["language"];
  responseSpeed: VoiceSessionPreferences["responseSpeed"];
}): LiveConnectConfig {
  const latency = profileForResponseSpeed(params.responseSpeed);
  const lang = params.language ?? "es";

  return {
    responseModalities: [Modality.AUDIO],
    temperature: latency.temperature,
    maxOutputTokens: latency.maxOutputTokens,
    enableAffectiveDialog: false,
    thinkingConfig: { thinkingBudget: 0, includeThoughts: false },
    speechConfig: {
      voiceConfig: {
        prebuiltVoiceConfig: { voiceName: params.voiceName },
      },
    },
    systemInstruction: `${params.systemInstruction}\n\n${sessionLanguageInstruction(lang)}`,
    inputAudioTranscription: {},
    outputAudioTranscription: {},
    proactivity: { proactiveAudio: false },
    realtimeInputConfig: {
      automaticActivityDetection: {
        disabled: false,
        startOfSpeechSensitivity: StartSensitivity.START_SENSITIVITY_HIGH,
        endOfSpeechSensitivity: EndSensitivity.END_SENSITIVITY_HIGH,
        prefixPaddingMs: CED_VOICE_PROFILE_LOCK.live.prefixPaddingMs,
        silenceDurationMs: CED_VOICE_PROFILE_LOCK.live.silenceDurationMs,
      },
      activityHandling: ActivityHandling.NO_INTERRUPTION,
    },
    contextWindowCompression: {
      slidingWindow: { targetTokens: "12800" },
    },
    tools: [{ functionDeclarations: [...LIVE_FUNCTION_DECLARATIONS] }],
  };
}
