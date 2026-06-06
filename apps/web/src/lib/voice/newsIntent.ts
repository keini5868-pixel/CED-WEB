const NEWS_PATTERNS = [
  /\bnoticia/i,
  /\bnoticias/i,
  /\bactualidad/i,
  /\binvestig/i,
  /\b(u\s*l\s*t\s*i\s*m|últim|ultim)/i,
  /\bbusca(r|me)?\b.*\b(noticia|hoy|actual)/i,
  /\bqu[eé]\s+pas[oó]/i,
  /\bhoy\s+en\b/i,
  /\bresumen\b.*\bhoy\b/i,
  /\bnews\b/i,
  /\btitulares\b/i,
  /\bperiódico/i,
  /\bdiario\b/i,
  /\bcu[eé]ntame\b.*\b(hoy|noticia)/i,
  /\bdime\b.*\b(noticia|hoy|ultim)/i,
  /\bdame\b.*\b(noticia|resumen)/i,
  /\binforme\b.*\bhoy\b/i,
  /\bde\s+cir\b.*\b(hoy|ultim|notic)/i,
  /\b(lo|las|los)\s+(últim|ultim)/i,
];

/** Detecta petición de noticias o actualidad (español / spanglish). */
export function normalizeTranscript(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/\bno\s+ticia\s*s?\b/g, "noticias")
    .replace(/\b(u\s*l\s*t\s*i\s*m\w*)/g, "ultimas")
    .replace(/\bpu\s+ede\s+s\b/g, "puedes")
    .replace(/\bde\s+cir\b/g, "decir")
    .trim();
}

/** Detecta petición de noticias o actualidad (español / spanglish). */
export function isNewsIntent(text: string): boolean {
  const raw = text.trim();
  if (raw.length < 6) return false;

  const t = normalizeTranscript(raw);
  const compact = t.replace(/\s/g, "");

  if (NEWS_PATTERNS.some((p) => p.test(t))) return true;

  if (/ultimasno|noticiasdehoy|noticiadehoy|investiganoticias/.test(compact)) {
    return true;
  }

  if (/\bultim\w*\b/.test(t) && /\b(no|noti|hoy)\b/.test(t)) return true;

  return false;
}
