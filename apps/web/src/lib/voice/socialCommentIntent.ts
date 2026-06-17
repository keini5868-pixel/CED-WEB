/** Intención de leer comentarios en redes sociales. */

const UNSUPPORTED_PLATFORMS =
  /\b(github|twitter|x\.com|tiktok|youtube|whatsapp|telegram|linkedin|discord)\b/i;

export function isUnsupportedCommentPlatform(text: string): boolean {
  const t = text.trim();
  return UNSUPPORTED_PLATFORMS.test(t) && /\bcomentarios?\b/i.test(t);
}

export function isSocialCommentReadIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 8) return false;
  if (isUnsupportedCommentPlatform(t)) return false;
  const hasPlatform = /\b(instagram|facebook|meta|redes|ig|fb)\b/i.test(t);
  const hasCommentCue =
    /\bcomentarios?\b/i.test(t) ||
    /\b(revisa|revisar|revisate|revis[aá]me|revisalo|checa|mira|lee|leer|listado|lista)\b/i.test(t) ||
    /\b(nuevos?|recientes?)\b/i.test(t) ||
    /\bdime\s+s[ií]\b/i.test(t) ||
    /\btengo\b.*\b(nuevos?|comentarios?)\b/i.test(t);
  if (hasPlatform && hasCommentCue) return true;
  return /\bcomentarios?\b/i.test(t) && hasCommentCue;
}

export function socialCommentPlatform(text: string): "instagram" | "facebook" | "both" {
  const t = text.toLowerCase();
  const ig = /\b(instagram|ig)\b/.test(t);
  const fb = /\b(facebook|fb)\b/.test(t);
  if (ig && !fb) return "instagram";
  if (fb && !ig) return "facebook";
  return "both";
}
