/** @deprecated Usa @/lib/api/openai */
export {
  fetchDeepAnalysis,
  fetchRealtimeSession,
  fetchVoiceBrief,
} from "@/lib/api/openai";
export type {
  RealtimeSessionResponse,
  RealtimeSessionResponse as EphemeralTokenResponse,
  VoiceBriefResponse,
} from "@/lib/api/openai";

import { fetchRealtimeSession } from "@/lib/api/openai";

/** Compat legacy Gemini ephemeral token → OpenAI Realtime session */
export async function fetchEphemeralToken(voiceName?: string) {
  const res = await fetchRealtimeSession(voiceName);
  if (!res.ok) return res;
  return {
    ok: true as const,
    token: res.clientSecret,
    clientSecret: res.clientSecret,
    model: res.model,
    voiceName: res.voiceName,
    systemInstruction: res.systemInstruction,
    expiresInSeconds: res.expiresInSeconds,
  };
}
