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
        "La sesión de voz se detuvo por cupo. Recargue o intente más tarde.",
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
        "Límite de uso de voz alcanzado. Revise su plan o intente más tarde.",
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
        "Conflicto de audio. Desactive y vuelva a activar el micrófono.",
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
      userMessage: "La sesión de voz no pudo continuar. Intente de nuevo.",
    };
  }

  return { unexpected: true, code, reason, recoverable: true };
}
