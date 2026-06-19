/** Intents para generar imágenes por voz. */

const GENERATE_IMAGE_PATTERNS = [
  /\b(genera|generar|crea|cresa|crear|dise[nñ]a|haz(me)?|dame)\s+(?:una?\s+)?imagen\b/i,
  /\b(genera|crea|haz|dame)\s+(?:un|una)\s+(?:logo|banner|flyer|portada|arte|gr[aá]fico)\b/i,
  /\bimagen\s+de\b/i,
  /\bpaint\s+(?:an?\s+)?image\b/i,
  /\b(?:logo|banner|flyer)\s+(?:de|para|con)\b/i,
];

export function isGenerateImageIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 8) return false;
  return GENERATE_IMAGE_PATTERNS.some((p) => p.test(t));
}

export function parseGenerateImagePrompt(text: string): string | null {
  const t = text.trim();
  const patterns = [
    /\b(?:genera|generar|crea|cresa|crear|dise[nñ]a|haz|dame)\s+(?:una?\s+)?imagen\s+(?:de|con|que\s+diga|que\s+sea)?\s*[:.]?\s*(.+)$/i,
    /\b(?:genera|crea|haz|dame)\s+(?:un|una)\s+(?:logo|banner|flyer|portada|gr[aá]fico)\s+(?:de|con|para)?\s*[:.]?\s*(.+)$/i,
    /\bimagen\s+de\s+(.+)$/i,
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
