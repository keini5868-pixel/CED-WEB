/** Fusiona chunks de transcripción streaming (delta o acumulativo). */

export function mergeTranscriptChunk(previous: string, chunk: string): string {
  const prev = previous.trim();
  const next = chunk.trim();
  if (!next) return prev;
  if (!prev) return next;
  if (next.startsWith(prev)) return next;
  if (prev.startsWith(next)) return prev;
  if (prev.endsWith(next) || next.endsWith(prev)) {
    return next.length >= prev.length ? next : prev;
  }
  return `${prev} ${next}`;
}

/**
 * Decide si un turno nuevo del agente debe pegarse al anterior.
 * Causa raíz de duplicación: el HUD unía dos respuestas distintas en <45s.
 */
export function resolveAgentTranscriptMerge(
  previous: string,
  incoming: string,
  opts: { sameStream: boolean; incomingPartial?: boolean; previousPartial?: boolean },
): { action: "merge" | "replace" | "new"; text: string } {
  const prev = (previous || "").trim();
  const next = (incoming || "").trim();
  if (!next) return { action: "merge", text: prev };
  if (!prev) return { action: "new", text: next };

  if (opts.sameStream || opts.incomingPartial || opts.previousPartial) {
    return { action: "merge", text: mergeTranscriptChunk(prev, next) };
  }

  if (next.startsWith(prev) && next.length > prev.length + 24) {
    const suffix = next.slice(prev.length).replace(/^[\s.,;:—-]+/, "");
    if (suffix.length >= 24) {
      return { action: "new", text: suffix };
    }
    return { action: "replace", text: next };
  }
  if (prev.startsWith(next)) {
    return { action: "replace", text: prev };
  }

  return { action: "new", text: next };
}

export function shouldSkipDuplicateAgentLine(
  previousTexts: string[],
  incoming: string,
): boolean {
  const next = (incoming || "").trim();
  if (!next) return true;
  return previousTexts.some((item) => (item || "").trim() === next);
}

/** Hint de idioma vía system instruction (native audio no usa languageCode). */
export function sessionLanguageInstruction(lang: "es" | "en" | "pt"): string {
  switch (lang) {
    case "es":
      return "IDIOMA SESIÓN: El usuario habla español latino (México). Responde SOLO en español. Transcribe el audio del usuario en español con caracteres latinos.";
    case "pt":
      return "IDIOMA SESIÓN: O usuário fala português brasileiro. Responda APENAS em português.";
    case "en":
      return "SESSION LANGUAGE: The user speaks English. Respond ONLY in English.";
    default:
      return sessionLanguageInstruction("es");
  }
}
