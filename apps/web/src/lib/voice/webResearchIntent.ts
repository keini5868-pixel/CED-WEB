/** Peticiones que requieren búsqueda web / datos actuales (legacy CED). */

import { isNewsIntent, normalizeTranscript } from "@/lib/voice/newsIntent";

const WEATHER_PATTERNS = [
  /\bclima\b/i,
  /\btemperatura/i,
  /\bpron[oó]stico/i,
  /\bqu[eé]\s+tiempo\s+hace\b/i,
  /\bc[oó]mo\s+est[aá]\s+el\s+(tiempo|clima)\b/i,
  /\btiempo\s+(de|en|hoy|actual)/i,
  /\b(hace|har[aá])\s+(fr[ií]o|calor|viento|sol)\b/i,
  /\b(clima|tiempo)\b.*\b(bueno|malo|bonito|feo|agradable)\b/i,
  /\bllueve\b/i,
  /\bgrados\b/i,
  /\bweather\b/i,
];

const WEB_PATTERNS = [
  /\binvestig/i,
  /\bbusca(r|me|lo|rlo)?\b/i,
  /\bbúscame\b/i,
  /\bbusca(r|me)?\b.*\b(internet|web|google|l[ií]nea|reddit)\b/i,
  /\b(informaci[oó]n|datos)\s+(sobre|de|acerca)\b/i,
  /\bbusca(r|me|lo)?\b.*\bqu[eé]\s+es\b/i,
  /\binformaci[oó]n actualizada\b/i,
  /\bdatos actuales\b/i,
  /\bclima\b/i,
  /\btiempo\b.*\b(hoy|actual)\b/i,
  /\bprecio\b.*\bhoy\b/i,
  /\bc[uú]anto cuesta hoy\b/i,
  /\bqu[eé] pasa con\b/i,
  /\bqu[eé] ha pasado\b/i,
  /\bhoy en\b/i,
  /\bactualidad\b/i,
];

export function isWeatherIntent(text: string): boolean {
  const t = normalizeTranscript(text);
  if (t.length < 6) return false;
  return WEATHER_PATTERNS.some((p) => p.test(t));
}

/** ¿El usuario pide buscar / investigar algo (creatina, noticias, clima, etc.)? */
export function isWebResearchIntent(text: string): boolean {
  if (isNewsIntent(text)) return true;
  if (isWeatherIntent(text)) return true;
  const t = normalizeTranscript(text);
  if (t.length < 8) return false;
  if (WEB_PATTERNS.some((p) => p.test(t))) {
    if (/\bbusca(r|me|lo)?\b/i.test(t) && t.length < 12) return false;
    return true;
  }
  return false;
}

/** ¿Enviar ACK en cuanto la intención sea clara (antes del turno final)? */
export function canEarlyWebSearch(text: string): boolean {
  if (!isWebResearchIntent(text)) return false;
  const t = normalizeTranscript(text);
  if (isWeatherIntent(text) || isNewsIntent(text)) return t.length >= 10;
  return t.length >= 14;
}

/** Usuario pregunta si ya hay resultado / si buscó. */
export function isSearchStatusIntent(text: string): boolean {
  const t = normalizeTranscript(text);
  return /\b(buscaste|busco|encontraste|conseguiste|tienes la info|ya tienes|todav[ií]a|hubo respuesta|d[oó]nde est[aá]|sistema.*carg|loading)\b/i.test(
    t,
  );
}

export type WebBriefKind = "news" | "weather" | "general";

export function webBriefKind(text: string): WebBriefKind {
  if (isWeatherIntent(text)) return "weather";
  if (isNewsIntent(text)) return "news";
  return "general";
}

export function webBriefTimeoutMs(kind: WebBriefKind): number {
  // Backend: Tavily ~8 s + Gemini ~14 s secuencial; margen para red.
  if (kind === "weather") return 22000;
  return 24000;
}

const ADVANCED_CONFIRM_ANSWER = /^(s[ií]|s[ií]\s+se[nñ]or|si\s+se[nñ]or|adelante|ok|vale|dale|de acuerdo|hazlo|confirmado|por favor|claro|exacto|correcto|bueno)[\s.!?,]*$/i;

const EXPLICIT_ADVANCED_PATTERNS = [
  /\bsistema avanzado\b/i,
  /\ban[aá]lisis profundo\b/i,
  /\banaliza(r|me)?\s+(en detalle|a fondo|profundo)\b/i,
  /\bconsulta(r|me)?\s+al sistema\b/i,
  /\bmodo (profundo|avanzado)\b/i,
  /\bactiva(r)?\s+el sistema avanzado\b/i,
];

const COMPLEX_ANALYSIS_PATTERNS = [
  /\ban[aá]lisis profundo\b/i,
  /\banaliza(r|me)?\s+(en detalle|a fondo|profundo)\b/i,
  /\bestrategia\b/i,
  /\bplan de acci[oó]n\b/i,
  /\bcompar(a|ar|me)\b.*\b(opciones|alternativas|pros y contras)\b/i,
  /\bventajas y desventajas\b/i,
  /\bimplicaciones\b/i,
  /\bescenarios\b/i,
  /\bpros y contras\b/i,
  /\broadmap\b/i,
  /\bframework\b/i,
];

/** Respuesta corta de confirmación (sí, adelante, ok). */
export function isAdvancedConfirmAnswer(text: string): boolean {
  const t = normalizeTranscript(text).trim();
  if (!t || t.length > 36) return false;
  if (ADVANCED_CONFIRM_ANSWER.test(t)) return true;
  const words = t.split(/\s+/);
  if (words.length <= 4 && /^(s[ií]|adelante|claro|dale|vale|ok)\b/i.test(t)) {
    return true;
  }
  return false;
}

/** @deprecated Usar isAdvancedConfirmAnswer */
export function hasAdvancedSystemConfirmation(text: string): boolean {
  return isAdvancedConfirmAnswer(text);
}

export function isExplicitAdvancedRequest(text: string): boolean {
  const t = normalizeTranscript(text);
  return EXPLICIT_ADVANCED_PATTERNS.some((p) => p.test(t));
}

/** Pregunta compleja que amerita sistema avanzado (no clima/noticias). */
export function isComplexAnalysisRequest(text: string): boolean {
  const t = normalizeTranscript(text);
  if (t.length < 12) return false;
  if (isWebResearchIntent(t) || isWeatherIntent(t) || isNewsIntent(t)) return false;
  return COMPLEX_ANALYSIS_PATTERNS.some((p) => p.test(t));
}

export function shouldAllowAdvancedTool(
  userText: string,
  toolPrompt: string,
  webFetchActive: boolean,
  confirmPending = false,
): boolean {
  if (webFetchActive) return false;
  if (isWebResearchIntent(userText) || isWebResearchIntent(toolPrompt)) return false;
  if (isWeatherIntent(userText) || isWeatherIntent(toolPrompt)) return false;

  if (isExplicitAdvancedRequest(userText) || isExplicitAdvancedRequest(toolPrompt)) {
    return true;
  }

  if (confirmPending && isAdvancedConfirmAnswer(userText)) {
    return true;
  }

  return false;
}
