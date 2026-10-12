/** Stop de presentación: calla hasta el siguiente «ok CED». */

const STOP_WORDS = new Set([
  "stop",
  "stopo",
  "stopa",
  "stoppo",
  "estop",
  "estopo",
  "istop",
  "etop",
  "eetop",
  "top",
  "stopp",
  "sstop",
  "stap",
  "stpo",
  "alto",
  "silencio",
  "callate",
  "calla",
  "cayate",
  "parate",
  "basta",
  "detente",
  "deten",
  "quieto",
  "para",
  "parar",
  "detener",
  "cancela",
  "cancelar",
]);
const STOP_SHAPE = /^(e+)?s+t+o+p+[aeiou]*$/;
const STOP_ECHO = new Set(["o", "oh", "a", "ah", "e", "eh", "p", "u"]);

const SHORT_STOP = new Set([
  "esto",
  "esta",
  "estoy",
  "es todo",
  "es top",
  "es stop",
  "e stop",
  "e top",
  "est op",
  "esstop",
  "s top",
  "es to",
  "esto p",
  "el esto",
  "un esto",
]);

const WAKE_LEAD = new Set([
  "ok",
  "okay",
  "okey",
  "okei",
  "okai",
  "oye",
  "hey",
  "ey",
]);
const WAKE_NAME = new Set([
  "ced",
  "set",
  "sec",
  "sed",
  "c",
  "ce",
  "seth",
  "said",
  "seid",
  "sit",
  "cet",
]);
const ADDRESS = new Set(["senor", "senora", "don", "dona"]);
const GLUE = new Set([
  "si",
  "dime",
  "digame",
  "hola",
  "oye",
  "escucha",
  "por",
  "favor",
  "adelante",
  "ya",
  "ahora",
  "entonces",
  "y",
  "e",
  "un",
  "el",
  "la",
  "me",
  "please",
  "and",
  "then",
  "ahi",
]);

function norm(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function editDistance(a: string, b: string): number {
  if (Math.abs(a.length - b.length) > 1) return 2;
  const prev: number[] = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const cur: number[] = [i];
    for (let j = 1; j <= b.length; j += 1) {
      const del = prev[j] ?? i;
      const ins = cur[j - 1] ?? i;
      const sub = prev[j - 1] ?? i - 1;
      cur.push(Math.min(del + 1, ins + 1, sub + (a[i - 1] === b[j - 1] ? 0 : 1)));
    }
    prev.length = 0;
    prev.push(...cur);
  }
  return prev[prev.length - 1] ?? 2;
}

function isName(token: string): boolean {
  if (WAKE_NAME.has(token)) return true;
  if (token.length < 2 || token.length > 5) return false;
  return ["ced", "set", "sec", "sed"].some((base) => editDistance(token, base) <= 1);
}

function isStopWord(token: string): boolean {
  if (STOP_WORDS.has(token)) return true;
  if (STOP_SHAPE.test(token)) return true;
  if (token.length >= 3 && token.length <= 6 && editDistance(token, "stop") <= 1) {
    return true;
  }
  return false;
}

function isStopCommand(tokens: string[]): boolean {
  if (!tokens.length || tokens.length > 8) return false;
  if (tokens.length <= 4 && STOP_SHAPE.test(tokens.join(""))) return true;
  if (!tokens.some(isStopWord)) return false;
  return tokens.every(
    (token) =>
      WAKE_LEAD.has(token) ||
      GLUE.has(token) ||
      ADDRESS.has(token) ||
      STOP_ECHO.has(token) ||
      isName(token) ||
      isStopWord(token),
  );
}

const LOOSE_STOP = /\b(s+t+o+p+[a-z]*|estop[a-z]*|stopo|stoppo|alto|callate|cayate|para|parar)\b/;

/** STT ruidoso: «shops», «esto» corto, etc. — solo para latch local de mute. */
export function mayBeStopHint(text: string): boolean {
  const t = norm(text);
  if (!t || t.length > 24) return false;
  if (isStopUtterance(text)) return true;
  if (LOOSE_STOP.test(t)) return true;
  const tokens = t.split(" ").filter(Boolean);
  if (tokens.length <= 3) {
    return tokens.some(
      (token) =>
        isStopWord(token) ||
        (token.length >= 3 && token.length <= 7 && editDistance(token, "stop") <= 1),
    );
  }
  return false;
}

export function isStopUtterance(text: string): boolean {
  let tokens = norm(text).split(" ").filter(Boolean);
  while (tokens.length && ADDRESS.has(tokens[tokens.length - 1] ?? "")) {
    tokens = tokens.slice(0, -1);
  }
  if (!tokens.length) return false;
  const folded = tokens.join(" ");
  if (isStopCommand(tokens)) return true;
  for (let size = 1; size <= Math.min(4, tokens.length); size += 1) {
    if (isStopCommand(tokens.slice(-size))) return true;
  }
  return tokens.length <= 4 && SHORT_STOP.has(folded);
}

export function isWakeUtterance(text: string): boolean {
  const tokens = norm(text).split(" ").filter(Boolean);
  if (tokens.length === 1) return isName(tokens[0] ?? "");
  return tokens.some(
    (token, index) => WAKE_LEAD.has(token) && isName(tokens[index + 1] ?? ""),
  );
}
