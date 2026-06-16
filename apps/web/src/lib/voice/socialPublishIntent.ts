/** Detección de intents para publicar en redes por voz (fallback si el modelo no invoca tool). */

function stripQuotes(s: string): string {
  return s.replace(/^["']|["']$/g, "").trim();
}

export type PublishPlatform = "facebook" | "instagram";

export function isPublishIntent(text: string): boolean {
  return /\b(publica|publicar|postea|postear|sube|subir|env[ií]a|enviar)\b/i.test(
    text.trim(),
  );
}

export function detectPublishPlatform(text: string): PublishPlatform | null {
  const t = text.toLowerCase();
  const hasIg = /\binstagram\b|\binsta\b|\big\b/.test(t);
  const hasFb = /\bfacebook\b|\bfb\b/.test(t);
  if (hasIg && !hasFb) return "instagram";
  if (hasFb && !hasIg) return "facebook";
  return null;
}

/** Confirmación corta o orden de ejecutar ("sí", "publica", "hazlo"). */
export function isPublishGoCommand(text: string): boolean {
  const t = text.trim();
  if (!t || t.length > 28) return false;
  return /^(publica(r|lo|la|los|las)?|env[ií]a(r|lo|la|los|las)?|hazlo|confirma(r)?|adelante|s[ií]|ok|dale|vale|claro)[\s.!?,]*$/i.test(
    t,
  );
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
  if (quoted?.[1]?.trim() && quoted[1].trim().length >= 3) {
    return stripQuotes(quoted[1]);
  }

  return null;
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
    if (body && body.length >= 3) {
      caption = stripQuotes(body);
      break;
    }
  }

  const quoted = t.match(/["'](.+?)["']/);
  if (quoted?.[1]?.trim() && quoted[1].trim().length >= 3) {
    caption = stripQuotes(quoted[1]);
  }

  if (urlMatch) {
    caption = caption.replace(urlMatch[0], "").trim();
  }

  if (!caption || caption.length < 3 || /^(esto|lo|la|en|con)$/i.test(caption)) {
    return null;
  }

  return {
    caption,
    imageUrl: urlMatch?.[0],
  };
}

export function hasExplicitPublishContent(
  text: string,
  platform: PublishPlatform,
): boolean {
  if (platform === "facebook") {
    return parseFacebookPublishMessage(text) !== null;
  }
  return parseInstagramPublishRequest(text) !== null;
}

/** Pide publicar en una red pero aún no dictó el texto del post. */
export function isPublishRequestWithoutContent(text: string): PublishPlatform | null {
  const platform = detectPublishPlatform(text);
  if (!platform || !isPublishIntent(text)) return null;
  if (hasExplicitPublishContent(text, platform)) return null;
  return platform;
}

/** Texto del post cuando el usuario responde sin repetir la red. */
export function parseStandalonePublishContent(text: string): string | null {
  const t = text.trim();
  if (t.length < 3 || t.length > 2000) return null;
  if (isPublishIntent(t) || detectPublishPlatform(t)) return null;
  if (isPublishGoCommand(t)) return null;
  return stripQuotes(t);
}

export function isSocialPublishIntent(text: string): boolean {
  return (
    parseFacebookPublishMessage(text) !== null ||
    parseInstagramPublishRequest(text) !== null ||
    isPublishRequestWithoutContent(text) !== null
  );
}
