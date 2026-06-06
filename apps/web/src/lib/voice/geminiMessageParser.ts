import type { LiveServerMessage } from "@google/genai";

type ModelPart = {
  text?: string;
  thought?: boolean;
  inlineData?: { data?: string; mimeType?: string };
};

/** Extrae audio PCM de parts — sin usar getters del SDK (evita warnings). */
export function extractAudioParts(
  message: LiveServerMessage,
): { data: string; mimeType: string }[] {
  const parts = message.serverContent?.modelTurn?.parts as ModelPart[] | undefined;
  if (!parts?.length) return [];

  const chunks: { data: string; mimeType: string }[] = [];
  for (const part of parts) {
    const inline = part.inlineData;
    if (inline?.data && inline.mimeType?.startsWith("audio/")) {
      chunks.push({
        data: inline.data,
        mimeType: inline.mimeType,
      });
    }
  }
  return chunks;
}

/** Texto del modelo excluyendo parts marcados como thought. */
export function extractModelText(message: LiveServerMessage): string | null {
  const parts = message.serverContent?.modelTurn?.parts as ModelPart[] | undefined;
  if (!parts?.length) return null;

  let text = "";
  for (const part of parts) {
    if (part.thought || typeof part.text !== "string" || !part.text) continue;
    text += part.text;
  }
  return text || null;
}
