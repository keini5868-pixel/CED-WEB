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
