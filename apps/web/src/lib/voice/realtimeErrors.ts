/** Errores recuperables de OpenAI Realtime que no deben bloquear la sesión de voz. */
export function isBenignRealtimeError(message: string): boolean {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("no active response") ||
    normalized.includes("cancellation failed") ||
    normalized.includes("response_cancel_not_active") ||
    normalized.includes("response cancel")
  );
}
