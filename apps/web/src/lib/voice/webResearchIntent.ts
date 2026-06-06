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

const ADVANCED_CONFIRM_PATTERNS = [
  /\b(s[ií]|s[ií]\s+se[nñ]or|si\s+se[nñ]or)\b/i,
  /\badelante\b/i,
  /\bconsulta(lo|me|lo)?\b/i,
  /\bpor favor\b/i,
  /\bconfirma(do)?\b/i,
  /\bhazlo\b/i,
  /\bde acuerdo\b/i,
];

/** Usuario confirmó explícitamente consultar al sistema avanzado. */
export function hasAdvancedSystemConfirmation(text: string): boolean {
  const t = normalizeTranscript(text);
  return ADVANCED_CONFIRM_PATTERNS.some((p) => p.test(t));
}

export function shouldAllowAdvancedTool(
  userText: string,
  toolPrompt: string,
  webFetchActive: boolean,
): boolean {
  if (webFetchActive) return false;
  if (isWebResearchIntent(userText) || isWebResearchIntent(toolPrompt)) {
    return false;
  }
  if (isWeatherIntent(userText) || isWeatherIntent(toolPrompt)) return false;
  return hasAdvancedSystemConfirmation(userText);
}
