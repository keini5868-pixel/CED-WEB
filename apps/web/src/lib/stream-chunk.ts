/**
 * Agrega un chunk SSE al texto visible — tolera deltas o buffers acumulados.
 */
export function appendStreamChunk(current: string, chunk: string): string {
  const prev = current || "";
  const incoming = chunk || "";
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
