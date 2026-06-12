import { cedApiPath } from "@/lib/api/ced-proxy";

/** Convierte URL de imagen de la API a proxy same-origin (funciona en chat y voz). */
export function normalizeCedMediaUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return trimmed;
  if (trimmed.startsWith("/api/ced/")) return trimmed;
  if (trimmed.startsWith("data:")) return trimmed;

  try {
    const parsed = new URL(trimmed, "https://ced.local");
    const match = parsed.pathname.match(/\/(?:v1\/)?media\/publish\/([^/?#]+)/i);
    if (match?.[1]) {
      return cedApiPath(`media/publish/${decodeURIComponent(match[1])}`);
    }
  } catch {
    /* ignore */
  }
  return trimmed;
}
