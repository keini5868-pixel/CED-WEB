import type { GeminiVoiceId } from "@ced/types";

export type OpenAIVoiceOption = {
  id: GeminiVoiceId;
  name: string;
  label: string;
  description: string;
  gender: string;
  style: string;
};

/** Voces OpenAI Realtime (2026). */
export const OPENAI_VOICE_OPTIONS: OpenAIVoiceOption[] = [
  { id: "alloy", name: "Alloy", label: "Alloy", description: "Neutral, equilibrada", gender: "Neutral", style: "Profesional" },
  { id: "echo", name: "Echo", label: "Echo", description: "Masculina, clara", gender: "Masculina", style: "Directa" },
  { id: "shimmer", name: "Shimmer", label: "Shimmer", description: "Femenina, cálida", gender: "Femenina", style: "Cálida" },
  { id: "ash", name: "Ash", label: "Ash", description: "Suave, profesional", gender: "Neutral", style: "Suave" },
  { id: "ballad", name: "Ballad", label: "Ballad", description: "Expresiva", gender: "Neutral", style: "Expresiva" },
  { id: "coral", name: "Coral", label: "Coral", description: "Amigable", gender: "Femenina", style: "Amigable" },
  { id: "sage", name: "Sage", label: "Sage", description: "Calmada, consultora", gender: "Neutral", style: "Consultora" },
  { id: "verse", name: "Verse", label: "Verse", description: "Dinámica", gender: "Neutral", style: "Dinámica" },
];

/** @deprecated alias — migración Gemini → OpenAI */
export const GEMINI_VOICE_OPTIONS = OPENAI_VOICE_OPTIONS;

export function normalizeVoiceName(name: string | undefined): GeminiVoiceId {
  const n = (name ?? "").trim().toLowerCase();
  const known = OPENAI_VOICE_OPTIONS.some((v) => v.id === n);
  if (known) return n;
  return "alloy";
}
