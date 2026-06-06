import type { EphemeralTokenResponse } from "@/lib/api/gemini";
import { fetchEphemeralToken } from "@/lib/api/gemini";
import { loadVoicePreferences } from "@/lib/voice/preferences";

type CachedToken = EphemeralTokenResponse & { ok: true; cachedAt: number };

let cache: CachedToken | null = null;
let inflight: Promise<EphemeralTokenResponse> | null = null;

const TTL_MS = 4 * 60 * 1000;

function isFresh(entry: CachedToken): boolean {
  return Date.now() - entry.cachedAt < TTL_MS;
}

export function getCachedEphemeralToken(
  voiceName?: string,
): (EphemeralTokenResponse & { ok: true }) | null {
  if (!cache || !isFresh(cache)) return null;
  if (voiceName && cache.voiceName !== voiceName) return null;
  return cache;
}

export function prefetchEphemeralToken(voiceName?: string): void {
  const name = voiceName ?? loadVoicePreferences().voiceName;
  if (getCachedEphemeralToken(name)) return;
  if (inflight) return;
  inflight = fetchEphemeralToken(name)
    .then((res) => {
      if (res.ok) {
        cache = { ...res, cachedAt: Date.now() };
      }
      return res;
    })
    .finally(() => {
      inflight = null;
    });
}

export async function fetchEphemeralTokenCached(
  voiceName?: string,
): Promise<EphemeralTokenResponse> {
  const cached = getCachedEphemeralToken(voiceName);
  if (cached) return cached;
  if (inflight) return inflight;
  const res = await fetchEphemeralToken(voiceName);
  if (res.ok) {
    cache = { ...res, cachedAt: Date.now() };
  }
  return res;
}

export function clearEphemeralTokenCache(): void {
  cache = null;
}
