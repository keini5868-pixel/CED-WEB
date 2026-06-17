/** Intents de búsqueda visual — cámara + internet. */

const VISUAL_SEARCH_PATTERNS = [
  /\bbusca(r|me|lo)?\b.*\b(internet|web|google|l[ií]nea)\b.*\b(veo|ves|muestr|camara|c[aá]mara|esto|eso)\b/i,
  /\b(qu[eé]|cu[aá]nto)\b.*\b(es|cuesta|vale|significa)\b.*\b(esto|eso|lo que)\b/i,
  /\bbusca(r|me)?\b.*\b(lo que|esto que)\b.*\b(veo|ves|muestro|ense[nñ]o)\b/i,
  /\binvestiga(r|me)?\b.*\b(lo que|esto)\b.*\b(veo|ves|muestr)\b/i,
  /\b(qu[eé] es esto)\b/i,
  /\bbusca esto en internet\b/i,
  /\bbusca lo que ves\b/i,
  /\bbusca lo que est[aá]s viendo\b/i,
];

const REMEMBER_PATTERNS = [
  /\brecuerda(r)?\s+que\b/i,
  /\bguarda(r)?\s+en\s+memoria\b/i,
  /\bno\s+olvides\s+que\b/i,
  /\banota(r)?\s+que\b/i,
];

const MEMORY_RECALL_PATTERNS = [
  /\b(qu[eé]|que)\s+recuerdas\b/i,
  /\brecuerdas\s+(sobre|de|mi|mis)\b/i,
  /\b(qu[eé]|que)\s+guardaste\b/i,
  /\bbusca(r)?\s+en\s+memoria\b/i,
];

const PROSPECTION_ON = [
  /\bactiva(r)?\s+prospecci[oó]n\b/i,
  /\bactiva(r)?\b.*\bprospecci[oó]n\b/i,
  /\bactivamos\b.*\bprospecci[oó]n\b/i,
  /\bmodo\s+prospecci[oó]n\b/i,
  /\bmodo\b.*\bprospecci[oó]n\b/i,
  /\bmodo\s+perspectiva\b/i,
  /\bperspective\s+mode\b/i,
  /\bencender\s+prospecci[oó]n\b/i,
];

const PROSPECTION_OFF = [
  /\bdesactiva(r)?\s+prospecci[oó]n\b/i,
  /\bapaga(r)?\s+prospecci[oó]n\b/i,
];

const PROSPECTION_REPORT = [
  /\b(reporte|informe)\s+de\s+(leads|prospecci[oó]n)\b/i,
  /\bc[uú]antos\s+leads\b/i,
  /\bleads\s+de\s+hoy\b/i,
];

export function isVisualSearchIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 8) return false;
  return VISUAL_SEARCH_PATTERNS.some((p) => p.test(t));
}

export function isRememberIntent(text: string): boolean {
  return REMEMBER_PATTERNS.some((p) => p.test(text.trim()));
}

export function parseRememberContent(text: string): { key: string; content: string } | null {
  const t = text.trim();
  const m = t.match(
    /(?:recuerda(?:r)?\s+que|guarda(?:r)?\s+en\s+memoria|no\s+olvides\s+que|anota(?:r)?\s+que)\s+(.+)/i,
  );
  if (!m?.[1]) return null;
  const content = m[1].trim();
  const key = content.slice(0, 40).replace(/\s+/g, "_").toLowerCase() || "nota";
  return { key, content };
}

export function isMemoryRecallIntent(text: string): boolean {
  return MEMORY_RECALL_PATTERNS.some((p) => p.test(text.trim()));
}

export function isProspectionOnIntent(text: string): boolean {
  return PROSPECTION_ON.some((p) => p.test(text.trim()));
}

export function isProspectionOffIntent(text: string): boolean {
  return PROSPECTION_OFF.some((p) => p.test(text.trim()));
}

export function isProspectionReportIntent(text: string): boolean {
  return PROSPECTION_REPORT.some((p) => p.test(text.trim()));
}

const SHORT_AFFIRMATION =
  /^(ahora\s+s[ií]|s[ií]|ok|vale|dale|perfecto|claro|bueno|listo|de acuerdo)[\s.!?,]*$/i;

/** Evita falsos positivos por "Ahora sí", eco, preposición o "modo protección". */
export function userExplicitlyRequestedProspection(text: string): boolean {
  const t = text.trim();
  if (!t || t.length < 12) return false;
  if (SHORT_AFFIRMATION.test(t)) return false;
  if (/\bprotecci[oó]n\b/i.test(t)) return false;
  if (/\bpreposici[oó]n\b/i.test(t)) return false;
  if (/\bprostitu/i.test(t)) return false;
  if (/\btranspos/i.test(t)) return false;
  if (!/\bprospecci[oó]n\b/i.test(t) && !/\bmodo\s+perspectiva\b/i.test(t) && !/\bperspective\s+mode\b/i.test(t)) {
    return false;
  }
  return isProspectionOnIntent(t);
}
