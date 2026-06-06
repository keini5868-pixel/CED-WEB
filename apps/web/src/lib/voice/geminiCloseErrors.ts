export type GeminiCloseInfo = {
  unexpected: boolean;
  code?: number;
  reason?: string;
  /** false = no reintentar (billing, policy, auth). */
  recoverable: boolean;
  userMessage?: string;
};

export function classifyGeminiClose(
  unexpected: boolean,
  event?: Pick<CloseEvent, "code" | "reason">,
): GeminiCloseInfo {
  const code = event?.code;
  const reason = event?.reason ?? "";

  if (!unexpected) {
    return { unexpected: false, code, reason, recoverable: false };
  }

  const reasonLower = reason.toLowerCase();

  if (
    code === 1011 &&
    (reasonLower.includes("credit") ||
      reasonLower.includes("prepayment") ||
      reasonLower.includes("depleted") ||
      reasonLower.includes("billing") ||
      reasonLower.includes("quota"))
  ) {
    return {
      unexpected: true,
      code,
      reason,
      recoverable: false,
      userMessage:
        "Créditos de Gemini agotados. Recarga en AI Studio (ai.studio/projects) y vuelve a activar el micrófono.",
    };
  }

  if (
    reasonLower.includes("resource_exhausted") ||
    reasonLower.includes("429")
  ) {
    return {
      unexpected: true,
      code,
      reason,
      recoverable: false,
      userMessage:
        "Límite de uso de Gemini alcanzado. Revisa tu plan o créditos en AI Studio.",
    };
  }

  if (
    code === 1007 &&
    reasonLower.includes("activity control")
  ) {
    return {
      unexpected: true,
      code,
      reason,
      recoverable: true,
      userMessage:
        "Conflicto de VAD en Gemini. Desactiva y vuelve a activar el micrófono.",
    };
  }

  if (
    code === 1007 ||
    reasonLower.includes("unsupported language")
  ) {
    return {
      unexpected: true,
      code,
      reason,
      recoverable: false,
      userMessage:
        "Configuración de idioma incompatible con el modelo de voz. Recarga la página (Ctrl+Shift+R).",
    };
  }

  if (code === 1008 || reasonLower.includes("policy")) {
    return {
      unexpected: true,
      code,
      reason,
      recoverable: false,
      userMessage: "Gemini rechazó la sesión por política de uso.",
    };
  }

  return { unexpected: true, code, reason, recoverable: true };
}
