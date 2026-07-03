/** Colapsa parciales de streaming (voz) en un solo mensaje por turno. */

export type StreamCollapsibleMessage = {
  role: string;
  content: string;
  created_at?: string | null;
};

export function collapseStreamingMessages<T extends StreamCollapsibleMessage>(
  messages: T[],
): T[] {
  const out: T[] = [];
  for (const msg of messages) {
    const content = (msg.content || "").trim();
    if (!content) continue;

    const isAssistant = msg.role === "model" || msg.role === "assistant";
    if (!isAssistant) {
      out.push({ ...msg, content });
      continue;
    }

    const prev = out[out.length - 1];
    const prevIsAssistant =
      prev && (prev.role === "model" || prev.role === "assistant");
    if (prevIsAssistant) {
      const prevContent = (prev.content || "").trim();
      if (content.startsWith(prevContent) && content.length > prevContent.length) {
        out[out.length - 1] = { ...msg, content };
        continue;
      }
      if (prevContent.startsWith(content) && prevContent.length >= content.length) {
        continue;
      }
    }
    out.push({ ...msg, content });
  }
  return out;
}
