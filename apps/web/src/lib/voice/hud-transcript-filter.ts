/** Filtra metadata interna (tool calls, código) del HUD visual — espejo de voice_response_guard.py */

const CODE_LEAK =
  /tool_code|end_of_tool_code|print\s*\(|```|\bdef\s+\w+\s*\(|import\s+\w+|function\s+\w+\s*\(/i;

/** buscar_direccion(direccion='...'), publicar_facebook(mensaje='...'), etc. */
const TOOL_INVOKE =
  /\b[a-z_][a-z0-9_]*\s*\(\s*[a-z_]+\s*=/i;

const TOOL_INVOKE_ONLY = /^[a-z_][a-z0-9_]*\s*\([^)]*\)\s*\.?$/i;

export function shouldHideHudTranscript(text: string): boolean {
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return true;
  if (CODE_LEAK.test(cleaned)) return true;
  if (TOOL_INVOKE.test(cleaned)) return true;
  if (TOOL_INVOKE_ONLY.test(cleaned)) return true;
  return false;
}

export function sanitizeHudTranscript(text: string): string | null {
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  if (!cleaned || shouldHideHudTranscript(cleaned)) return null;
  return cleaned;
}
