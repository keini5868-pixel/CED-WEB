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

/** Usuario quiere crear/contenido para una publicación (no publicar aún). */
export function isPublishPlanningIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 10) return false;
  return (
    /\b(voy a hacer|vamos a hacer|quiero hacer|necesito hacer|har[eé]|voy a crear|quiero crear)\s+(?:una?\s+)?(?:publicaci[oó]n|post|contenido|pieza)\b/i.test(
      t,
    ) ||
    /\b(ay[uú]dame|ayudame|ap[oó]yame)\s+(?:a\s+)?(?:con\s+)?(?:una?\s+)?(?:publicaci[oó]n|post|contenido)\b/i.test(
      t,
    ) ||
    /\b(prepara(r|me)?|arma(r|me)?|desarrolla(r|me)?)\s+(?:una?\s+)?(?:publicaci[oó]n|post)\b/i.test(
      t,
    )
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

/** Confirmación única o orden de ejecutar ("sí", "publica", "envíalo"). */
export function isPublishGoCommand(text: string): boolean {
  const t = text.trim();
  if (!t || t.length > 80) return false;
  if (
    /^(publica(?:r|lo|la|los|las)?(\s+as[ií])?|env[ií]a(?:r|lo|la|los|las)?|m[aá]ndalo|hazlo|confirma(?:r)?|adelante|s[ií]|ok|dale|vale|claro|perfecto|exacto|as[ií]\s+es|de acuerdo)[\s.!?,]*$/i.test(
      t,
    )
  ) {
    return true;
  }
  if (t.length <= 40 && /\b(s[ií]\s+)?(publica(?:lo|la)?|env[ií]alo|m[aá]ndalo|hazlo)\b/i.test(t)) {
    return true;
  }
  // "no, ya publicación" / "ya, hazlo" / "nada más"
  if (
    t.length <= 72 &&
    /\b(ya|nada\s+m[aá]s|sin\s+m[aá]s|directo|publicaci[oó]n|hazlo|publica(?:lo|la)?)\b/i.test(t)
  ) {
    return true;
  }
  return false;
}

/** Publicar de inmediato sin más preguntas. */
export function isPublishDirectCommand(text: string): boolean {
  return /\b(publica(?:lo|la)?\s+ya|env[ií]a(?:lo|la)?\s+ya|m[aá]ndalo|hazlo\s+ya|sin\s+m[aá]s|directo|ahora\s+s[ií]|ya\s+mismo)\b/i.test(
    text.trim(),
  );
}

/** Extrae texto de publicación aunque no diga "facebook" explícitamente. */
export function parseDirectPublishContent(text: string): {
  platform: PublishPlatform;
  content: string;
} | null {
  const t = text.trim();
  if (t.length < 8 || !isPublishIntent(t)) return null;

  const platform = detectPublishPlatform(t) ?? "facebook";
  const patterns = [
    /\b(?:publica(?:r)?|postea(?:r)?|sube(?:r)?)\s+(?:en\s+(?:facebook|instagram|fb|insta|ig)\s+)?(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$/i,
    /\bquiero\s+publicar\s+(?:en\s+\w+\s+)?(?:que\s+)?(?:diga\s+)?[:.]?\s*(.+)$/i,
    /\b(?:publica|postea)\s+[:.]?\s*(.+)$/i,
  ];

  for (const pattern of patterns) {
    const m = t.match(pattern);
    const body = m?.[1]?.trim();
    if (
      body &&
      body.length >= 3 &&
      !/^(en|que|diga|dice|esto|lo|la|ya|facebook|instagram|fb|insta)$/i.test(body)
    ) {
      return { platform, content: stripQuotes(body) };
    }
  }

  const quoted = t.match(/["'](.+?)["']/);
  if (quoted?.[1]?.trim() && quoted[1].trim().length >= 3) {
    return { platform, content: stripQuotes(quoted[1]) };
  }

  return null;
}

export function parsePublishIdea(text: string): {
  platform: PublishPlatform | null;
  idea: string;
} | null {
  const t = text.trim();
  if (!isPublishPlanningIntent(t) && !isPublishIntent(t)) return null;

  const platform = detectPublishPlatform(t);
  const ideaPatterns = [
    /\b(?:sobre|acerca de|de|para|promocionando|promover)\s+(.+)$/i,
    /\b(?:publicaci[oó]n|post|contenido)\s+(?:sobre|de|para)\s+(.+)$/i,
    /\b(?:idea|tema)\s*[:.]?\s*(.+)$/i,
  ];

  for (const pattern of ideaPatterns) {
    const m = t.match(pattern);
    const idea = m?.[1]?.trim();
    if (idea && idea.length >= 8) {
      return { platform, idea: stripQuotes(idea) };
    }
  }

  if (t.length >= 24) {
    return { platform, idea: t };
  }
  return null;
}

export function parseFacebookPublishMessage(text: string): string | null {
  const direct = parseDirectPublishContent(text);
  if (direct?.platform === "facebook") return direct.content;
  if (direct?.platform === "instagram") return null;

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

/** Pide publicar en una red sin texto final listo. */
export function isPublishRequestWithoutContent(text: string): PublishPlatform | null {
  const platform = detectPublishPlatform(text);
  if (!platform || !isPublishIntent(text)) return null;
  if (hasExplicitPublishContent(text, platform)) return null;
  return platform;
}

export function isSocialPublishIntent(text: string): boolean {
  return (
    parseFacebookPublishMessage(text) !== null ||
    parseInstagramPublishRequest(text) !== null ||
    isPublishRequestWithoutContent(text) !== null ||
    isPublishPlanningIntent(text)
  );
}
