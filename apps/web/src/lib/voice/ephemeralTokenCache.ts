import type { RealtimeSessionOptions } from "@/lib/api/openai";
import type { RealtimeSessionResponse } from "@/lib/api/openai";
import { fetchRealtimeSession } from "@/lib/api/openai";
import { loadVoicePreferences } from "@/lib/voice/preferences";

type CachedToken = RealtimeSessionResponse & {
  ok: true;
  cachedAt: number;
  cacheKey: string;
};

let cache: CachedToken | null = null;
let inflight: Promise<RealtimeSessionResponse> | null = null;

const TTL_MS = 4 * 60 * 1000;

function sessionOptionsFromPrefs(
  voiceName?: string,
  options?: Partial<RealtimeSessionOptions>,
): { voiceName: string; options: RealtimeSessionOptions } {
  const prefs = loadVoicePreferences();
  return {
    voiceName: voiceName ?? prefs.voiceName,
    options: {
      language: options?.language ?? prefs.language,
      responseSpeed: options?.responseSpeed ?? prefs.responseSpeed,
      voicePace: options?.voicePace ?? prefs.voicePace,
      voiceWarmth: options?.voiceWarmth ?? prefs.voiceWarmth,
      voiceEnergy: options?.voiceEnergy ?? prefs.voiceEnergy,
    },
  };
}

function buildCacheKey(voiceName?: string, options?: Partial<RealtimeSessionOptions>): string {
  const { voiceName: name, options: opts } = sessionOptionsFromPrefs(voiceName, options);
  return `${name}:${opts.language}:${opts.responseSpeed}:${opts.voicePace}:${opts.voiceWarmth}:${opts.voiceEnergy}`;
}

function isFresh(entry: CachedToken): boolean {
  return Date.now() - entry.cachedAt < TTL_MS;
}

export function getCachedEphemeralToken(
  voiceName?: string,
  options?: Partial<RealtimeSessionOptions>,
): (RealtimeSessionResponse & { ok: true }) | null {
  if (!cache || !isFresh(cache)) return null;
  if (cache.cacheKey !== buildCacheKey(voiceName, options)) return null;
  return cache;
}

export function prefetchEphemeralToken(
  voiceName?: string,
  options?: Partial<RealtimeSessionOptions>,
): void {
  const key = buildCacheKey(voiceName, options);
  if (getCachedEphemeralToken(voiceName, options)) return;
  if (inflight) return;
  const { voiceName: name, options: opts } = sessionOptionsFromPrefs(voiceName, options);
  inflight = fetchRealtimeSession(name, opts)
    .then((res) => {
      if (res.ok) {
        cache = { ...res, cachedAt: Date.now(), cacheKey: key };
      }
      return res;
    })
    .finally(() => {
      inflight = null;
    });
}

export async function fetchEphemeralTokenCached(
  voiceName?: string,
  options?: Partial<RealtimeSessionOptions>,
): Promise<RealtimeSessionResponse> {
  const cached = getCachedEphemeralToken(voiceName, options);
  if (cached) return cached;
  if (inflight) return inflight;
  const key = buildCacheKey(voiceName, options);
  const { voiceName: name, options: opts } = sessionOptionsFromPrefs(voiceName, options);
  const res = await fetchRealtimeSession(name, opts);
  if (res.ok) {
    cache = { ...res, cachedAt: Date.now(), cacheKey: key };
  }
  return res;
}

export function clearEphemeralTokenCache(): void {
  cache = null;
}
