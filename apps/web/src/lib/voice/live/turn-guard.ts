/** Evita que eco / VAD rearmen el mismo turno y CED se quede repitiendo. */

export const POST_SPEECH_ECHO_MS = 3500;
export const SAME_UTTERANCE_COOLDOWN_MS = 20_000;

export function normalizeVoiceUtterance(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function isSameVoiceUtterance(a: string, b: string): boolean {
  const x = normalizeVoiceUtterance(a);
  const y = normalizeVoiceUtterance(b);
  if (!x || !y) return false;
  if (x === y) return true;
  if (x.length >= 12 && y.length >= 12 && (x.includes(y) || y.includes(x))) {
    return true;
  }
  const xWords = x.split(" ").filter((w) => w.length > 2);
  const ySet = new Set(y.split(" ").filter((w) => w.length > 2));
  if (xWords.length >= 3 && ySet.size >= 3) {
    const hits = xWords.filter((w) => ySet.has(w)).length;
    if (hits / Math.max(xWords.length, ySet.size) >= 0.78) return true;
  }
  return false;
}

/** True si este transcript ya se contestó hace poco — no crear otra respuesta. */
export function shouldSkipAlreadyAnswered(opts: {
  incoming: string;
  lastAnswered: string;
  lastAnsweredAt: number;
  now: number;
  cooldownMs?: number;
}): boolean {
  const cooldown = opts.cooldownMs ?? SAME_UTTERANCE_COOLDOWN_MS;
  if (!opts.lastAnswered.trim() || !opts.incoming.trim()) return false;
  if (opts.now - opts.lastAnsweredAt > cooldown) return false;
  return isSameVoiceUtterance(opts.incoming, opts.lastAnswered);
}
