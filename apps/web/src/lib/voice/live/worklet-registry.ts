/** Registra AudioWorklet una sola vez por AudioContext (evita NotSupportedError). */

import { createWorkletFromSrc } from "@/lib/voice/live/worklet-loader";

const loadedContexts = new WeakSet<AudioContext>();

export async function ensureAudioWorkletModule(
  ctx: AudioContext,
  workletName: string,
  workletClassSrc: string,
): Promise<void> {
  if (loadedContexts.has(ctx)) return;

  const blobUrl = createWorkletFromSrc(workletName, workletClassSrc);
  try {
    await ctx.audioWorklet.addModule(blobUrl);
    loadedContexts.add(ctx);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("already registered")) {
      loadedContexts.add(ctx);
      return;
    }
    throw err;
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
}
