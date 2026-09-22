/** Whisper/STT inventa esto con silencio o ruido — no es dictado real. */
const JUNK_RE =
  /amara(?:\.org)?|subt[ií]tulos?(?:\s+realizados)?|subtitles?\s+by|comunidad\s+de\s+amara|thanks\s+for\s+watching|thank you for watching|transcripci[oó]n\s+autom[aá]tica|subtitulos?\s+amara|^\s*\(?\s*music\s*\)?\s*$/i;

export function sanitizeDictationTranscript(text: string): string {
  const raw = (text || "").trim();
  if (!raw) return "";
  if (raw.length <= 2) return "";
  if (JUNK_RE.test(raw) && raw.length < 96) return "";
  if (/^(you|thank you|thanks|music)$/i.test(raw)) return "";
  return raw;
}

/** El toque de soltar dictado no debe encender el asistente CED. */
let assistLockUntil = 0;

export function markDictationAssistLock(ms = 900): void {
  assistLockUntil = Date.now() + ms;
}

export function isDictationAssistLocked(): boolean {
  return Date.now() < assistLockUntil;
}
