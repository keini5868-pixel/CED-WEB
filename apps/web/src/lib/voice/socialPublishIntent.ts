/** Detección de intents para publicar en redes por voz (fallback si el modelo no invoca tool). */

function stripQuotes(s: string): string {
  return s.replace(/^["']|["']$/g, "").trim();
}

export function parseFacebookPublishMessage(text: string): string | null {
  const t = text.trim();
  if (t.length < 8) return null;
  if (!/\bfacebook\b/i.test(t)) return null;
  if (!/\b(publica|publicar|post|postea|sube|subir|haz(me)?\s+un\s+post|esto)\b/i.test(t)) {
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
    if (body && body.length >= 3 && !/^(en|que|diga|dice|esto|lo)$/i.test(body)) {
      return stripQuotes(body);
    }
  }

  const quoted = t.match(/["'](.+?)["']/);
  if (quoted?.[1]?.trim()) return stripQuotes(quoted[1]);

  if (/\b(publica|publicar|postea)\b/i.test(t) && /\besto\b/i.test(t)) {
    return "Publicación CED";
  }

  return "Publicación CED";
}

export function parseInstagramPublishRequest(text: string): {
  caption: string;
  imageUrl?: string;
} | null {
  const t = text.trim();
  if (!/\binstagram\b/i.test(t)) return null;
  if (!/\b(publica|publicar|post|postea|sube|subir|esto)\b/i.test(t)) return null;

  const urlMatch = t.match(/https?:\/\/[^\s]+/i);
  const patterns = [
    /\b(?:publica(?:r)?|postea(?:r)?|sube(?:r)?)\s+(?:en\s+)?instagram\s+(?:con\s+la\s+foto\s+)?(?:que\s+)?(?:diga|dice)?\s*[:.]?\s*(.+)$/i,
    /\bpost\s+en\s+instagram\s*[:.]?\s*(.+)$/i,
  ];

  let caption = "";
  for (const pattern of patterns) {
    const m = t.match(pattern);
    const body = m?.[1]?.trim();
    if (body && body.length >= 2) {
      caption = stripQuotes(body);
      break;
    }
  }

  const quoted = t.match(/["'](.+?)["']/);
  if (quoted?.[1]?.trim()) {
    caption = stripQuotes(quoted[1]);
  }

  if (urlMatch) {
    caption = caption.replace(urlMatch[0], "").trim();
  }

  if (!caption || /^(esto|lo|la|en|con)$/i.test(caption)) {
    caption = "Publicación CED";
  }

  return {
    caption,
    imageUrl: urlMatch?.[0],
  };
}

export function isSocialPublishIntent(text: string): boolean {
  return (
    parseFacebookPublishMessage(text) !== null ||
    parseInstagramPublishRequest(text) !== null
  );
}
