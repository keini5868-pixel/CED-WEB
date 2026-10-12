/** Encender cámara: solo «CED enciende la cámara». GRABAR y el resto no. */

import { isStopUtterance } from "@/lib/voice/stopLatch";

export type CameraIntent = "activate" | "deactivate" | null;

const CED_NAME = String.raw`(?:ced|set|sec|sed|c|ce|seth|said|seid|sit|cet)`;

const ACTIVATE_PATTERN = new RegExp(
  String.raw`\b(?:ok(?:ay|ey)?\s+|oye\s+)?${CED_NAME}\b.{0,24}\benciende(?:r|a)?\s+(?:la\s+)?c[aá]mara\b`,
  "i",
);

const DEACTIVATE_PATTERNS = [
  /\bya\s+no\s+mires\b/i,
  /\bapaga(r)?\s+la\s+c[aá]mara\b/i,
  /\bdesactiva(r)?\s+la\s+c[aá]mara\b/i,
  /\bced[,]?\s*ya\s+no\s+mires\b/i,
  /\bdeja\s+de\s+mirar\b/i,
];

export function parseCameraIntent(transcript: string): CameraIntent {
  const text = transcript.trim();
  if (!text || isStopUtterance(text)) return null;
  for (const pattern of DEACTIVATE_PATTERNS) {
    if (pattern.test(text)) return "deactivate";
  }
  if (ACTIVATE_PATTERN.test(text)) return "activate";
  return null;
}

/** Única frase de voz que puede encender el hardware. GRABAR no. */
export function isCameraOpenUtterance(transcript: string): boolean {
  return parseCameraIntent(transcript) === "activate";
}
