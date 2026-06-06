/** Detección de intents de cámara en transcripciones (español). */

export type CameraIntent = "activate" | "deactivate" | null;

const ACTIVATE_PATTERNS = [
  /\bced[,]?\s*mira\b/i,
  /\bmira\s+esto\b/i,
  /\bmira\s+lo\s+que\s+tengo\b/i,
  /\bmira\s+esta\s+imagen\b/i,
  /\bven[,]?\s*mira\b/i,
  /\bactiva(r)?\s+la\s+c[aá]mara\b/i,
  /\benciende\s+la\s+c[aá]mara\b/i,
  /\bquiero\s+que\s+veas\b/i,
];

const DEACTIVATE_PATTERNS = [
  /\bya\s+no\s+mires\b/i,
  /\bapaga(r)?\s+la\s+c[aá]mara\b/i,
  /\bdesactiva(r)?\s+la\s+c[aá]mara\b/i,
  /\bced[,]?\s*ya\s+no\s+mires\b/i,
  /\bdeja\s+de\s+mirar\b/i,
];

export function parseCameraIntent(transcript: string): CameraIntent {
  const text = transcript.trim();
  if (!text) return null;
  for (const pattern of DEACTIVATE_PATTERNS) {
    if (pattern.test(text)) return "deactivate";
  }
  for (const pattern of ACTIVATE_PATTERNS) {
    if (pattern.test(text)) return "activate";
  }
  return null;
}
