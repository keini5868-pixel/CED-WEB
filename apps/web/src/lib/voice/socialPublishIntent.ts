/** Detección de intents para publicar en redes por voz (fallback si el modelo no invoca tool). */

export function parseFacebookPublishMessage(text: string): string | null {
  const t = text.trim();
  if (t.length < 10) return null;
  if (!/\bfacebook\b/i.test(t)) return null;
  if (!/\b(publica|publicar|post|postea|sube|subir|haz(me)?\s+un\s+post)\b/i.test(t)) {
    return null;
  }

  const patterns = [
    /\b(?:publica(?:r)?|postea(?:r)?|sube(?:r)?)\s+(?:en\s+)?facebook\s+(?:que\s+)?(?:diga|dice|con\s+el\s+texto)?\s*[:.]?\s*(.+)$/i,
    /\bhaz(?:me)?\s+un\s+post\s+en\s+facebook\s+(?:que\s+)?(?:diga|dice)?\s*[:.]?\s*(.+)$/i,
    /\bpost\s+en\s+facebook\s*[:.]?\s*(.+)$/i,
    /\bfacebook\s*[:.]?\s*(.+)$/i,
  ];

  for (const pattern of patterns) {
    const m = t.match(pattern);
    const body = m?.[1]?.trim();
    if (body && body.length >= 3 && !/^(en|que|diga|dice)$/i.test(body)) {
      return body.replace(/^["']|["']$/g, "").trim();
    }
  }
  return null;
}

export function parseInstagramPublishRequest(text: string): {
  caption: string;
  imageUrl?: string;
} | null {
  const t = text.trim();
  if (!/\binstagram\b/i.test(t)) return null;
  if (!/\b(publica|publicar|post|postea)\b/i.test(t)) return null;

  const urlMatch = t.match(/https?:\/\/[^\s]+/i);
  const captionMatch = t.match(
    /\b(?:publica(?:r)?|postea(?:r)?)\s+(?:en\s+)?instagram\s+(?:con\s+la\s+foto\s+)?(?:que\s+)?(?:diga|dice)?\s*[:.]?\s*(.+)$/i,
  );
  let caption = captionMatch?.[1]?.trim().replace(/^["']|["']$/g, "") ?? "";
  if (urlMatch) {
    caption = caption.replace(urlMatch[0], "").trim();
  }
  if (!caption && !urlMatch) return null;
  return {
    caption: caption || "Publicación CED",
    imageUrl: urlMatch?.[0],
  };
}

export function isSocialPublishIntent(text: string): boolean {
  return (
    parseFacebookPublishMessage(text) !== null ||
    parseInstagramPublishRequest(text) !== null
  );
}
