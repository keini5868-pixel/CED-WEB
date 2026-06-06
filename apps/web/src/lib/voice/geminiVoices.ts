import type { GeminiVoiceId } from "@ced/types";

export type GeminiVoiceOption = {
  id: GeminiVoiceId;
  name: string;
  gender: "F" | "M";
  style: string;
};

/** Voces oficiales Gemini Live (jun 2026). */
export const GEMINI_VOICE_OPTIONS: GeminiVoiceOption[] = [
  { id: "Aoede", name: "Aoede", gender: "F", style: "Suave · default" },
  { id: "Kore", name: "Kore", gender: "F", style: "Firme" },
  { id: "Leda", name: "Leda", gender: "F", style: "Juvenil" },
  { id: "Zephyr", name: "Zephyr", gender: "F", style: "Brillante" },
  { id: "Charon", name: "Charon", gender: "M", style: "Informativo" },
  { id: "Puck", name: "Puck", gender: "M", style: "Optimista" },
  { id: "Fenrir", name: "Fenrir", gender: "M", style: "Enérgico" },
  { id: "Orus", name: "Orus", gender: "M", style: "Firme" },
  { id: "Umbriel", name: "Umbriel", gender: "F", style: "Relajada" },
  { id: "Erinome", name: "Erinome", gender: "F", style: "Clara" },
  { id: "Laomedeia", name: "Laomedeia", gender: "F", style: "Animada" },
  { id: "Achernar", name: "Achernar", gender: "F", style: "Suave" },
  { id: "Gacrux", name: "Gacrux", gender: "F", style: "Madura" },
  { id: "Sulafat", name: "Sulafat", gender: "F", style: "Cálida" },
  { id: "Iapetus", name: "Iapetus", gender: "M", style: "Claro" },
  { id: "Algieba", name: "Algieba", gender: "M", style: "Smooth" },
  { id: "Schedar", name: "Schedar", gender: "M", style: "Uniforme" },
  { id: "Achird", name: "Achird", gender: "M", style: "Amigable" },
];

export const VALID_VOICE_IDS = new Set(GEMINI_VOICE_OPTIONS.map((v) => v.id));

export function normalizeVoiceName(name: string | undefined): GeminiVoiceId {
  if (name && VALID_VOICE_IDS.has(name)) return name;
  return "Aoede";
}
