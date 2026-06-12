/** Preferencia de tratamiento — "llámame señor", género, etc. */

export type UserGender = "male" | "female" | "neutral";

const ADDRESS_PATTERNS: Array<{ re: RegExp; group: number }> = [
  { re: /ll[aá]mame\s+(se[nñ]or[a]?|don|do[nñ]a|[\wáéíóúñ]+)/i, group: 1 },
  { re: /dime\s+(se[nñ]or[a]?|don|do[nñ]a|[\wáéíóúñ]+)/i, group: 1 },
  {
    re: /quiero\s+que\s+me\s+(?:digas|llames|trates)\s+(?:de\s+|como\s+)?(se[nñ]or[a]?|don|do[nñ]a|[\wáéíóúñ]+)/i,
    group: 1,
  },
  { re: /tr[aá]tame\s+de\s+(se[nñ]or[a]?|don|do[nñ]a|[\wáéíóúñ]+)/i, group: 1 },
  {
    re: /(?:desde\s+ahora|a\s+partir\s+de\s+ahora)\s+(?:ll[aá]mame|dime)\s+(se[nñ]or[a]?|don|do[nñ]a|[\wáéíóúñ]+)/i,
    group: 1,
  },
];

const GENDER_MALE = [/\bsoy\s+hombre\b/i, /\bsoy\s+var[oó]n\b/i, /\bsoy\s+masculino\b/i];
const GENDER_FEMALE = [/\bsoy\s+mujer\b/i, /\bsoy\s+femenin[ao]\b/i];
const GENDER_NEUTRAL = [/\bprefiero\s+sin\s+t[ií]tulo\b/i, /\bsin\s+se[nñ]or\b/i];

function normalizeHonorific(raw: string): string {
  const t = raw.trim();
  const low = t.toLowerCase().replace(/\./g, "");
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
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function parseAddressPreference(text: string): string | null {
  const t = text.trim();
  if (t.length < 6) return null;
  for (const { re, group } of ADDRESS_PATTERNS) {
    const m = t.match(re);
    const raw = m?.[group]?.trim();
    if (raw && raw.length >= 2) return normalizeHonorific(raw);
  }
  return null;
}

export function parseGenderPreference(text: string): UserGender | null {
  const t = text.trim();
  if (GENDER_MALE.some((p) => p.test(t))) return "male";
  if (GENDER_FEMALE.some((p) => p.test(t))) return "female";
  if (GENDER_NEUTRAL.some((p) => p.test(t))) return "neutral";
  return null;
}

export function isAddressPreferenceIntent(text: string): boolean {
  return parseAddressPreference(text) !== null || parseGenderPreference(text) !== null;
}
