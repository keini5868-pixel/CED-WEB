import type { GeminiVoiceId } from "@ced/types";

export type OpenAIVoiceOption = {
  id: GeminiVoiceId;
  name: string;
  label: string;
  description: string;
  gender: string;
  style: string;
  /** Etiqueta opcional en selector (p. ej. voces GA premium). */
  badge?: "NUEVA" | "PREMIUM";
};

/** Voces OpenAI Realtime (GA gpt-realtime, 2025+). */
export const OPENAI_VOICE_OPTIONS: OpenAIVoiceOption[] = [
  {
    id: "cedar",
    name: "Cedar",
    label: "Cedar",
    description: "Premium, natural, ideal Jarvis",
    gender: "Masculina",
    style: "Ejecutiva",
    badge: "NUEVA",
  },
  {
    id: "marin",
    name: "Marin",
    label: "Marin",
    description: "Premium, cálida y expresiva",
    gender: "Femenina",
    style: "Premium",
    badge: "NUEVA",
  },
  { id: "alloy", name: "Alloy", label: "Alloy", description: "Neutral, equilibrada", gender: "Neutral", style: "Profesional" },
  { id: "echo", name: "Echo", label: "Echo", description: "Masculina, clara — Jarvis clásico", gender: "Masculina", style: "Ejecutiva" },
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
  return "ash";
}
