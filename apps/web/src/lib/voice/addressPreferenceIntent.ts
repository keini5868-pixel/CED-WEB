/** Preferencia de tratamiento — "llámame señor", género, etc. */

export type UserGender = "male" | "female" | "neutral";

const HON = String.raw`(se[nñ]or[a]?|don|do[nñ]a)`;

const ADDRESS_PATTERNS: Array<{ re: RegExp; group: number }> = [
  { re: new RegExp(`ll[aá]mame\\s+${HON}\\b`, "i"), group: 1 },
  { re: new RegExp(`dime\\s+${HON}\\b`, "i"), group: 1 },
  {
    re: new RegExp(
      `quiero\\s+que\\s+me\\s+(?:digas|llames|trates)\\s+(?:de\\s+|como\\s+)?${HON}\\b`,
      "i",
    ),
    group: 1,
  },
  { re: new RegExp(`tr[aá]tame\\s+de\\s+${HON}\\b`, "i"), group: 1 },
  {
    re: new RegExp(
      `(?:desde\\s+ahora|a\\s+partir\\s+de\\s+ahora)\\s+(?:ll[aá]mame|dime)\\s+${HON}\\b`,
      "i",
    ),
    group: 1,
  },
];

const GENDER_MALE = [/\bsoy\s+hombre\b/i, /\bsoy\s+var[oó]n\b/i, /\bsoy\s+masculino\b/i];
const GENDER_FEMALE = [/\bsoy\s+mujer\b/i, /\bsoy\s+femenin[ao]\b/i];
const GENDER_NEUTRAL = [/\bprefiero\s+sin\s+t[ií]tulo\b/i, /\bsin\s+se[nñ]or\b/i];

/** "Dime si tengo comentarios" NO es cambio de tratamiento. */
export function shouldSkipAddressPreference(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (/\bdime\s+s[ií]\b/i.test(t)) return true;
  if (/\b(comentarios?|instagram|facebook|github|meta|publicar|clima|busca|prospecci)\b/i.test(t)) {
    return true;
  }
  if (/\?/.test(t)) return true;
  if (/^(dime|diga|ind[ií]came|cu[eé]ntame)\b/i.test(t) && !/\b(se[nñ]or|don|do[nñ]a)\b/i.test(t)) {
    return true;
  }
  return false;
}

function normalizeHonorific(raw: string): string | null {
  const t = raw.trim();
  if (!t) return null;
  const low = t.toLowerCase().replace(/\./g, "");
  if (low.length < 3 || /^(si|sí|se|me|te|lo|la|que|ke|ok|va)$/.test(low)) return null;
  const map: Record<string, string> = {
    senor: "Señor",
    señor: "Señor",
    sr: "Señor",
    senora: "Señora",
    señora: "Señora",
    sra: "Señora",
    don: "Don",
    dona: "Doña",
    doña: "Doña",
  };
  if (map[low]) return map[low];
  return null;
}

export function parseAddressPreference(text: string): string | null {
  if (shouldSkipAddressPreference(text)) return null;
  const t = text.trim();
  if (/^se[nñ]or[.!?,]*$/i.test(t)) return "Señor";
  if (/^se[nñ]ora[.!?,]*$/i.test(t)) return "Señora";
  if (t.length < 8) return null;
  for (const { re, group } of ADDRESS_PATTERNS) {
    const m = t.match(re);
    const raw = m?.[group]?.trim();
    if (!raw) continue;
    const normalized = normalizeHonorific(raw);
    if (normalized) return normalized;
  }
  return null;
}

export function parseGenderPreference(text: string): UserGender | null {
  if (shouldSkipAddressPreference(text)) return null;
  const t = text.trim();
  if (GENDER_MALE.some((p) => p.test(t))) return "male";
  if (GENDER_FEMALE.some((p) => p.test(t))) return "female";
  if (GENDER_NEUTRAL.some((p) => p.test(t))) return "neutral";
  return null;
}

export function isAddressPreferenceIntent(text: string): boolean {
  return parseAddressPreference(text) !== null || parseGenderPreference(text) !== null;
}
