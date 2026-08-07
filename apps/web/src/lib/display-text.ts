/**
 * Convierte cualquier valor API/SSE a texto visible.
 * Evita el clásico "[object Object]" al renderizar respuestas largas o errores.
 */
export function coerceDisplayText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "bigint") return value.toString();

  if (Array.isArray(value)) {
    // FastAPI 422: [{loc, msg, type}, ...]
    const parts = value
      .map((item) => {
        if (item == null) return "";
        if (typeof item === "string" || typeof item === "number") {
          return String(item);
        }
        if (typeof item === "object") {
          const row = item as Record<string, unknown>;
          if (typeof row.msg === "string" && row.msg.trim()) return row.msg;
          if (typeof row.message === "string" && row.message.trim()) {
            return row.message;
          }
          if (typeof row.text === "string" && row.text.trim()) return row.text;
          // OpenAI-style content parts
          if (row.type === "text" && typeof row.text === "string") {
            return row.text;
          }
        }
        return coerceDisplayText(item);
      })
      .map((s) => s.trim())
      .filter(Boolean);
    return parts.join("\n");
  }

  if (typeof value === "object") {
    const row = value as Record<string, unknown>;
    for (const key of [
      "text",
      "content",
      "reply",
      "response",
      "message",
      "msg",
      "detail",
      "body",
      "summary",
    ] as const) {
      if (key in row && row[key] != null && row[key] !== value) {
        const nested = coerceDisplayText(row[key]);
        if (nested.trim()) return nested;
      }
    }
    // Último recurso: JSON legible, nunca "[object Object]"
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }

  return "";
}

/** Alias semántico para errores API (detail puede ser string | object | array). */
export function formatApiDetail(
  detail: unknown,
  fallback = "Error del servidor",
): string {
  const text = coerceDisplayText(detail).trim();
  return text || fallback;
}
