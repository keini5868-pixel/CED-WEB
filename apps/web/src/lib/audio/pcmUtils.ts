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
  if (inputSampleRate <= 16000) return pcm;
  const ratio = inputSampleRate / 16000;
  const outLen = Math.floor(pcm.length / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i += 1) {
    out[i] = pcm[Math.floor(i * ratio)] ?? 0;
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
