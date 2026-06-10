import type { RealtimeSessionResponse } from "@/lib/api/openai";
import { fetchRealtimeSession } from "@/lib/api/openai";
import { loadVoicePreferences } from "@/lib/voice/preferences";

type CachedToken = RealtimeSessionResponse & { ok: true; cachedAt: number };

let cache: CachedToken | null = null;
let inflight: Promise<RealtimeSessionResponse> | null = null;

const TTL_MS = 4 * 60 * 1000;

function isFresh(entry: CachedToken): boolean {
  return Date.now() - entry.cachedAt < TTL_MS;
}

export function getCachedEphemeralToken(
  voiceName?: string,
): (RealtimeSessionResponse & { ok: true }) | null {
  if (!cache || !isFresh(cache)) return null;
  if (voiceName && cache.voiceName !== voiceName) return null;
  return cache;
}

export function prefetchEphemeralToken(voiceName?: string): void {
  const name = voiceName ?? loadVoicePreferences().voiceName;
  if (getCachedEphemeralToken(name)) return;
  if (inflight) return;
  inflight = fetchRealtimeSession(name)
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
): Promise<RealtimeSessionResponse> {
  const cached = getCachedEphemeralToken(voiceName);
  if (cached) return cached;
  if (inflight) return inflight;
  const res = await fetchRealtimeSession(voiceName);
  if (res.ok) {
    cache = { ...res, cachedAt: Date.now() };
  }
  return res;
}

export function clearEphemeralTokenCache(): void {
  cache = null;
}
