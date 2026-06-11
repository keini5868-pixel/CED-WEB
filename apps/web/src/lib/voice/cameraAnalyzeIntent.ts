/** Preguntas sobre lo visible en cámara (identificar, no buscar en web). */

const CAMERA_ANALYZE_PATTERNS = [
  /\b(qu[eé]|que)\s+(ves|veo|hay|est[aá])\s+(en\s+)?(la\s+)?c[aá]mara\b/i,
  /\b(qu[eé]|que)\s+es\s+(esto|eso)\b/i,
  /\bidentifica(r|me)?\b.*\b(veo|ves|muestro|c[aá]mara|esto|eso)\b/i,
  /\b(qu[eé]|que)\s+(tienes|tengo)\s+(en\s+)?(frente|la\s+c[aá]mara)\b/i,
  /\b(qu[eé]|que)\s+estoy\s+mostrando\b/i,
  /\b(qu[eé]|que)\s+ves\s+(ah[ií]|en\s+pantalla)\b/i,
  /\b(dime|cu[eé]ntame)\s+(qu[eé]|que)\s+(ves|es)\b/i,
  /\bwhat\s+(is\s+this|do\s+you\s+see)\b/i,
];

export function isCameraAnalyzeIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 6) return false;
  return CAMERA_ANALYZE_PATTERNS.some((p) => p.test(t));
}

export function cameraAnalyzeQuestion(text: string): string {
  const t = text.trim();
  if (/\b(qu[eé]|que)\s+es\s+(esto|eso)\b/i.test(t)) {
    return "¿Qué es esto y descríbelo brevemente?";
  }
  if (t.length > 12) return t;
  return "¿Qué ves en la imagen? Descríbelo e identifica objetos principales.";
}
