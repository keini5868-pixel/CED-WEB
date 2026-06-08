/**
 * Perfil de voz CED — BLOQUEADO (may 2026).
 * No modificar sin re-validar voz en dashboard.
 * Ref: docs/VOICE_WORKING_CONFIG.md
 */

export const CED_VOICE_PROFILE_LOCK = {
  version: "2026-05-28",
  model: "gemini-2.5-flash-native-audio-preview-12-2025",
  apiVersion: "v1alpha" as const,
  defaultVoice: "Charon",
  defaultLanguage: "es" as const,
  defaultResponseSpeed: "fast" as const,

  audio: {
    uplinkSampleRate: 16000,
    downlinkSampleRate: 24000,
    captureWorkletChunkSamples: 2048,
    playbackBufferSize: 7680,
    playbackInitialBufferSec: 0.1,
    playbackScheduleAheadSec: 0.2,
  },

  live: {
    activityHandling: "NO_INTERRUPTION" as const,
    startOfSpeechSensitivity: "START_SENSITIVITY_HIGH" as const,
    endOfSpeechSensitivity: "END_SENSITIVITY_HIGH" as const,
    prefixPaddingMs: 20,
    silenceDurationMs: 280,
    turnCompleteDelayMs: 160,
    playbackDrainMaxMs: 2200,
    proactiveAudio: false,
    thinkingBudget: 0,
    contextWindowTargetTokens: "12800",
  },

  latencyProfiles: {
    fast: {
      temperature: 0.42,
      maxOutputTokens: 1024,
    },
    balanced: {
      temperature: 0.5,
      maxOutputTokens: 896,
    },
    thoughtful: {
      temperature: 0.6,
      maxOutputTokens: 1536,
    },
  },

  webSearch: {
    briefTimeoutMs: 10000,
    ackInstruction:
      '[CED_ACK] Di EXACTAMENTE una sola vez: "Buscando en internet." Luego CALLA hasta [CED_BRIEF]. No repitas confirmaciones.',
  },

  advancedSystem: {
    fetchTimeoutMs: 30000,
    maxSpokenChars: 520,
    ackInstruction:
      '[CED_ACK] Di EXACTAMENTE: "Consulto el sistema avanzado." Una sola frase. CALLA hasta [CED_BRIEF].',
  },

  backend: {
    systemPromptFile: "apps/api/app/domain/ced_live_voice_prompt.py",
    envModelKey: "GEMINI_LIVE_MODEL",
  },
} as const;
