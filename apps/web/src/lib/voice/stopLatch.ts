/** Stop de presentación: calla hasta el siguiente «ok CED». */

const STOP_WORDS = new Set([
  "stop",
  "estop",
  "istop",
  "etop",
  "eetop",
  "top",
  "stopp",
  "sstop",
  "stap",
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
]);

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

const WAKE_LEAD = new Set(["ok", "okay", "okey", "oye", "hey", "ey"]);
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
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const cur = [i];
    for (let j = 1; j <= b.length; j += 1) {
      cur.push(
        Math.min(
          prev[j] + 1,
          cur[j - 1] + 1,
          prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
        ),
      );
    }
    prev.splice(0, prev.length, ...cur);
  }
  return prev[prev.length - 1];
}

function isName(token: string): boolean {
  if (["ced", "set", "sec", "sed", "c", "ce"].includes(token)) return true;
  if (token.length < 2 || token.length > 5) return false;
  return ["ced", "set", "sec", "sed"].some((base) => editDistance(token, base) <= 1);
}

function isStopWord(token: string): boolean {
  if (STOP_WORDS.has(token)) return true;
  if (token.length < 3 || token.length > 5) return false;
  return editDistance(token, "stop") <= 1;
}

function isStopCommand(tokens: string[]): boolean {
  if (!tokens.length || tokens.length > 8) return false;
  if (!tokens.some(isStopWord)) return false;
  return tokens.every(
    (token) =>
      WAKE_LEAD.has(token) ||
      GLUE.has(token) ||
      ADDRESS.has(token) ||
      isName(token) ||
      isStopWord(token),
  );
}

export function isStopUtterance(text: string): boolean {
  let tokens = norm(text).split(" ").filter(Boolean);
  while (tokens.length && ADDRESS.has(tokens[tokens.length - 1])) {
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
  if (tokens.length === 1) return isName(tokens[0]);
  return tokens.some(
    (token, index) => WAKE_LEAD.has(token) && isName(tokens[index + 1] || ""),
  );
}
