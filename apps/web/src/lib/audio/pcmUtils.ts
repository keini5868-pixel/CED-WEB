/** Utilidades PCM — solo main thread (btoa/atob disponibles). */

export function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/** iOS suele ignorar sampleRate:16000 — re-muestrea a 16 kHz para Gemini Live. */
export function downsampleInt16To16k(
  pcm: Int16Array,
  inputSampleRate: number,
): Int16Array {
  return resampleInt16(pcm, inputSampleRate, 16000);
}

/** Re-muestrea PCM16 linealmente (p. ej. mic 48 kHz → OpenAI Realtime 24 kHz). */
export function resampleInt16(
  pcm: Int16Array,
  inputSampleRate: number,
  targetSampleRate: number,
): Int16Array {
  if (inputSampleRate === targetSampleRate) return pcm;
  if (inputSampleRate <= 0 || targetSampleRate <= 0) return pcm;

  const ratio = inputSampleRate / targetSampleRate;
  const outLen =
    inputSampleRate > targetSampleRate
      ? Math.floor(pcm.length / ratio)
      : Math.floor(pcm.length * (targetSampleRate / inputSampleRate));
  const out = new Int16Array(Math.max(outLen, 1));

  for (let i = 0; i < out.length; i += 1) {
    const srcIdx = i * ratio;
    const idx0 = Math.min(Math.floor(srcIdx), pcm.length - 1);
    const idx1 = Math.min(idx0 + 1, pcm.length - 1);
    const frac = srcIdx - idx0;
    out[i] = Math.round(pcm[idx0]! * (1 - frac) + pcm[idx1]! * frac);
  }
  return out;
}

export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 8192;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const slice = bytes.subarray(i, i + chunkSize);
    for (let j = 0; j < slice.length; j += 1) {
      binary += String.fromCharCode(slice[j] ?? 0);
    }
  }
  return btoa(binary);
}
