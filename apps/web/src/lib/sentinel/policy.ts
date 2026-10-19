/** Política Sentinel: local al dispositivo. No se envían URLs ni búsquedas. */

export const SENTINEL_POLICY_KEY = "ced.sentinel.policy.v1";
export const SENTINEL_HUD_SOURCE = "ced-sentinel-hud";
export const SENTINEL_EXT_SOURCE = "ced-sentinel-extension";
export const SENTINEL_CHROME_EXTENSION_ID = "lljjmaaeaablafifigijmfclaakglphi";
export const SENTINEL_CHROME_STORE_URL =
  "https://chromewebstore.google.com/detail/sentinel-privacy-for-ced/lljjmaaeaablafifigijmfclaakglphi";

export type SentinelPolicy = {
  v: 1;
  malware: boolean;
  doh: boolean;
  trackers: boolean;
  explosivos: boolean;
  armas: boolean;
  autolesion: boolean;
  updatedAt: string;
};

export type SentinelExtStats = {
  blocked: number;
  stripped: number;
  policyHits: number;
  connected: boolean;
};

export const DEFAULT_SENTINEL_POLICY: SentinelPolicy = {
  v: 1,
  malware: true,
  doh: true,
  trackers: true,
  explosivos: false,
  armas: false,
  autolesion: false,
  updatedAt: "",
};

const EXPLOSIVOS_RE =
  /\b(c[oó]mo\s+(hacer|fabricar|preparar)|how\s+to\s+(make|build|manufacture))\b.{0,40}\b(bomba|explosiv|c4|tnt|napalm|molotov)\b/i;
const ARMAS_RE =
  /\b(c[oó]mo\s+(hacer|fabricar|comprar)|how\s+to\s+(make|build|buy|ghost))\b.{0,40}\b(arma|pistola|rifle|ghost\s*gun|receiver)\b/i;
const AUTOLESION_RE =
  /\b(suicid|quitarme\s+la\s+vida|matarme|autolesi[oó]n|self[-\s]?harm|kill\s+myself|ending\s+my\s+life)\b/i;

export function emptyExtStats(): SentinelExtStats {
  return { blocked: 0, stripped: 0, policyHits: 0, connected: false };
}

export function normalizePolicy(raw: unknown): SentinelPolicy {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    v: 1,
    malware: o.malware !== false,
    doh: o.doh !== false,
    trackers: o.trackers !== false,
    explosivos: o.explosivos === true,
    armas: o.armas === true,
    autolesion: o.autolesion === true,
    updatedAt: typeof o.updatedAt === "string" ? o.updatedAt : "",
  };
}

export function loadSentinelPolicy(): SentinelPolicy {
  if (typeof window === "undefined") return { ...DEFAULT_SENTINEL_POLICY };
  try {
    const raw = window.localStorage.getItem(SENTINEL_POLICY_KEY);
    if (!raw) return { ...DEFAULT_SENTINEL_POLICY };
    return normalizePolicy(JSON.parse(raw) as unknown);
  } catch {
    return { ...DEFAULT_SENTINEL_POLICY };
  }
}

export function saveSentinelPolicy(policy: SentinelPolicy): SentinelPolicy {
  const next = {
    ...normalizePolicy(policy),
    updatedAt: new Date().toISOString(),
  };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SENTINEL_POLICY_KEY, JSON.stringify(next));
    window.postMessage(
      { source: SENTINEL_HUD_SOURCE, type: "POLICY", policy: next },
      "*",
    );
  }
  return next;
}

function utf8ToB64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64ToUtf8(b64: string): string {
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export function encodePolicyShare(policy: SentinelPolicy): string {
  return utf8ToB64(JSON.stringify(normalizePolicy(policy)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

export function decodePolicyShare(token: string): SentinelPolicy | null {
  try {
    const pad = token.length % 4 === 0 ? "" : "=".repeat(4 - (token.length % 4));
    const b64 = token.replace(/-/g, "+").replace(/_/g, "/") + pad;
    return normalizePolicy(JSON.parse(b64ToUtf8(b64)) as unknown);
  } catch {
    return null;
  }
}

export type SentinelPolicyHit = {
  category: "explosivos" | "armas" | "autolesion";
  message: string;
};

const MSG_EXPLOSIVOS =
  "Sentinel bloqueó esta consulta (fabricación de explosivos). La política está activa en esta cuenta y no se envió al modelo.";
const MSG_ARMAS =
  "Sentinel bloqueó esta consulta (armas). La política está activa en esta cuenta y no se envió al modelo.";
const MSG_AUTOLESION =
  "Si estás en crisis, pide ayuda ahora: en EE.UU. y Canadá llama o escribe al 988. " +
  "Si hay peligro inmediato, llama a emergencias locales. Recursos: https://www.iasp.info/suicidalthoughts/";

export function evaluateSentinelTextPolicy(
  policy: SentinelPolicy,
  text: string,
): SentinelPolicyHit | null {
  const t = (text || "").trim();
  if (!t) return null;
  if (policy.autolesion && AUTOLESION_RE.test(t)) {
    return { category: "autolesion", message: MSG_AUTOLESION };
  }
  if (policy.explosivos && EXPLOSIVOS_RE.test(t)) {
    return { category: "explosivos", message: MSG_EXPLOSIVOS };
  }
  if (policy.armas && ARMAS_RE.test(t)) {
    return { category: "armas", message: MSG_ARMAS };
  }
  return null;
}

export function sentinelChatReply(text: string): string | null {
  const hit = evaluateSentinelTextPolicy(loadSentinelPolicy(), text);
  return hit?.message ?? null;
}
