/** Alineado con apps/api/app/domain/chat_limits.py */
export const CHAT_MESSAGE_MAX_CHARS = 50_000;

export const CHAT_MESSAGE_TOO_LONG_ES =
  `Tu texto es demasiado largo (máximo ${CHAT_MESSAGE_MAX_CHARS} caracteres). ` +
  "Súbelo como archivo PDF o Word (.docx) con el botón de documento.";

export function assertChatMessageLength(text: string): string | null {
  if (text.length > CHAT_MESSAGE_MAX_CHARS) {
    return CHAT_MESSAGE_TOO_LONG_ES;
  }
  return null;
}
