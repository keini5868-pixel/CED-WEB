/** Intents para generar imágenes por voz y chat. */

const CREATE_VERBS =
  "(?:genera(?:r|me|nos|do)?|crea(?:r|me|nos|do)?|cr[eé]ame|gener[aá]me|haz(?:me|nos|lo|la)?|hacer(?:me)?|dise[nñ]a(?:r|me|nos|do)?|dibuja(?:r|me)?|pinta(?:r|me)?|dame|hazme)";

const IMAGE_NOUN =
  "(?:imagen|foto|picture|ilustraci[oó]n|dise[nñ]o|arte|gr[aá]fico|creativo|logo|banner|flyer|portada)";

const GENERATE_IMAGE_PATTERNS = [
  new RegExp(`\\b${CREATE_VERBS}\\s+(?:una?\\s+)?${IMAGE_NOUN}\\b`, "i"),
  new RegExp(`\\b${IMAGE_NOUN}\\s+(?:de|con|para)\\b`, "i"),
  new RegExp(`\\bquiero\\s+(?:que\\s+)?${CREATE_VERBS}\\s+(?:una?\\s+)?${IMAGE_NOUN}\\b`, "i"),
  new RegExp(`\\bnecesito\\s+(?:una?\\s+)?${IMAGE_NOUN}\\b`, "i"),
  new RegExp(`\\bpuedes\\s+${CREATE_VERBS}\\s+(?:una?\\s+)?${IMAGE_NOUN}\\b`, "i"),
  /\bpaint\s+(?:an?\s+)?image\b/i,
];

export function isGenerateImageIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 8) return false;
  return GENERATE_IMAGE_PATTERNS.some((p) => p.test(t));
}

export function parseGenerateImagePrompt(text: string): string | null {
  const t = text.trim();
  const patterns = [
    new RegExp(
      `\\b${CREATE_VERBS}\\s+(?:una?\\s+)?${IMAGE_NOUN}\\s+(?:de|con|para|que\\s+)?\\s*[:.]?\\s*(.+)$`,
      "i",
    ),
    new RegExp(`\\b${IMAGE_NOUN}\\s+de\\s+(.+)$`, "i"),
    new RegExp(
      `\\bquiero\\s+(?:que\\s+)?${CREATE_VERBS}\\s+(?:una?\\s+)?${IMAGE_NOUN}\\s+(?:de|con|para|que\\s+)?\\s*[:.]?\\s*(.+)$`,
      "i",
    ),
    new RegExp(
      `\\bnecesito\\s+(?:una?\\s+)?${IMAGE_NOUN}\\s+(?:de|con|para|que\\s+)?\\s*[:.]?\\s*(.+)$`,
      "i",
    ),
  ];
  for (const pattern of patterns) {
    const m = t.match(pattern);
    const body = m?.[1]?.trim();
    if (body && body.length >= 3) return body.replace(/^["']|["']$/g, "").trim();
  }
  if (isGenerateImageIntent(t)) return t;
  return null;
}

/** Publicar con imagen de cámara o última generada. */
export function wantsCameraImageForPublish(text: string): boolean {
  return /\b(con\s+la\s+c[aá]mara|lo\s+que\s+(veo|ves|muestro)|esta\s+foto|esta\s+imagen|la\s+foto)\b/i.test(
    text.trim(),
  );
}

export function wantsLastImageForPublish(text: string): boolean {
  const t = text.trim();
  if (
    /\b(la\s+imagen\s+generada|la\s+ultima\s+imagen|esa\s+imagen|imagen\s+que\s+generaste|imagen\s+del\s+chat|en\s+el\s+chat|te\s+acabo\s+de\s+enviar|adjunt[eé]|busqu[eé])\b/i.test(
      t,
    )
  ) {
    return true;
  }
  return (
    /\b(publica|publicar|postea|sube)\b/i.test(t) &&
    /\b(est[oa]|lo|la\s+foto|esta\s+imagen)\b/i.test(t)
  );
}
