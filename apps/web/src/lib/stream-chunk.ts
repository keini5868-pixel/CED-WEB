import { coerceDisplayText } from "@/lib/display-text";

/**
 * Agrega un chunk SSE al texto visible — tolera deltas o buffers acumulados.
 * Coerce a string para nunca acumular "[object Object]".
 */
export function appendStreamChunk(
  current: unknown,
  chunk: unknown,
): string {
  const prev = coerceDisplayText(current);
  const incoming = coerceDisplayText(chunk);
  if (!incoming) return prev;
  if (!prev) return incoming;
  if (incoming.startsWith(prev)) {
    return incoming;
  }
  if (prev.startsWith(incoming)) {
    return prev;
  }
  if (prev.endsWith(incoming)) {
    return prev;
  }
  return `${prev}${incoming}`;
}
