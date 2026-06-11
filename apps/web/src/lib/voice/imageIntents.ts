/** Intents para generar imágenes por voz. */

const GENERATE_IMAGE_PATTERNS = [
  /\b(genera|generar|crea|crear|dise[nñ]a|haz(me)?)\s+(?:una?\s+)?imagen\b/i,
  /\b(genera|crea|haz)\s+(?:un|una)\s+(?:logo|banner|flyer|portada|arte)\b/i,
  /\bimagen\s+de\b/i,
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
    /\b(?:genera|generar|crea|crear|dise[nñ]a|haz)\s+(?:una?\s+)?imagen\s+(?:de|con|que\s+diga|que\s+sea)?\s*[:.]?\s*(.+)$/i,
    /\b(?:genera|crea|haz)\s+(?:un|una)\s+(?:logo|banner|flyer|portada)\s+(?:de|con|para)?\s*[:.]?\s*(.+)$/i,
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
  return /\b(la\s+imagen\s+generada|la\s+ultima\s+imagen|esa\s+imagen|imagen\s+que\s+generaste)\b/i.test(
    text.trim(),
  );
}
