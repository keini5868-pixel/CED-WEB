/** Filtra metadata interna (tool calls, código) del HUD visual — espejo de voice_response_guard.py */



const CODE_LEAK =

  /tool_code|end_of_tool_code|print\s*\(|```|\bdef\s+\w+\s*\(|import\s+\w+|function\s+\w+\s*\(/i;



/** buscar_direccion(direccion='...'), publicar_facebook(mensaje='...'), etc. */

const TOOL_NAMED_ARG = /\b[a-z_][a-z0-9_]*\s*\(\s*[a-z_]+\s*=/i;



/** buscar_direccion('...'), analyze_camera_frame("...") — args posicionales */

const TOOL_SNAKE_CALL = /\b[a-z_][a-z0-9_]*(?:_[a-z0-9_]+)+\s*\(/i;



/** Línea que es solo una invocación de tool */

const TOOL_INVOKE_ONLY = /^[a-z_][a-z0-9_]*\s*\([^)]*\)\s*\.?$/i;



/** Fragmento parcial mientras streamea: buscar_direccion( */

const TOOL_PARTIAL = /\b[a-z_]{4,}(?:_\w+)+\s*\(?$/i;



/** Tool embebida en texto natural */

const TOOL_EMBEDDED =

  /\b(?:buscar_|publicar_|generate_|analyze_|consultar_|request_|activar_|desactivar_|leer_|recall_|save_)[a-z0-9_]*\s*\(/i;



export function shouldHideHudTranscript(text: string): boolean {

  const cleaned = (text || "").replace(/\s+/g, " ").trim();

  if (!cleaned) return true;

  if (CODE_LEAK.test(cleaned)) return true;

  if (TOOL_NAMED_ARG.test(cleaned)) return true;

  if (TOOL_SNAKE_CALL.test(cleaned)) return true;

  if (TOOL_INVOKE_ONLY.test(cleaned)) return true;

  if (TOOL_PARTIAL.test(cleaned)) return true;

  if (TOOL_EMBEDDED.test(cleaned)) return true;

  return false;

}



export function sanitizeHudTranscript(text: string): string | null {

  const cleaned = (text || "").replace(/\s+/g, " ").trim();

  if (!cleaned || shouldHideHudTranscript(cleaned)) return null;

  return cleaned;

}


