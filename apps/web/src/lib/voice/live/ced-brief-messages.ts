/** Instrucciones de voz CED — una sola utterance, sin prefijos duplicados. */

import type { UserAddressContext } from "@/lib/api/profile";

export function cedGreetingPhrase(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<UserAddressContext, "greetingPhraseJarvis" | "greetingPhraseStandard"> | null,
): string {
  return voiceProfile === "jarvis"
    ? address?.greetingPhraseJarvis || "Hola. ¿En qué trabajamos?"
    : address?.greetingPhraseStandard || "Hola. ¿En qué trabajamos?";
}

/** @deprecated Usar cedGreetingPhrase + response.create directo */
export function cedGreetingTurn(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<UserAddressContext, "greetingPhraseJarvis" | "greetingPhraseStandard"> | null,
): string {
  const phrase = cedGreetingPhrase(voiceProfile, address);
  return (
    "[CED_GREETING] Di EXACTAMENTE esta frase una sola vez, sin añadir nada antes ni después: " +
    `"${phrase}"` +
    " PROHIBIDO: segunda frase, repetir el saludo, listar capacidades o mencionar ventas."
  );
}

export function cedBriefTurn(spoken: string): string {
  const body = spoken.trim();
  return (
    "[CED_BRIEF] Lee en voz alta UNA sola vez el siguiente texto. " +
    "PROHIBIDO: muletillas previas (claro, perfecto, dale, listo, ok). " +
    "PROHIBIDO: repetir la misma idea dos veces. " +
    "PROHIBIDO: resumir si el texto es un análisis — preséntalo completo en pocas frases.\n\n" +
    body
  );
}

export function cedSearchStatusTurn(): string {
  return cedBriefTurn("Indícame qué quieres buscar y lo consulto en internet.");
}

export const CED_ADVANCED_CONFIRM_PHRASE = "¿Activamos análisis profundo?";

export function cedAdvancedAckTurn(): string {
  return cedBriefTurn("Un momento.");
}

/** Usuario confirmó publicar — forzar invocación de tool con el copy ya desarrollado. */
export function cedPublishConfirmTurn(platform: "facebook" | "instagram"): string {
  const tool = platform === "facebook" ? "publicar_facebook" : "publicar_instagram";
  return (
    "[CED_PUBLISH] El usuario confirmó. Invoca " +
    tool +
    " AHORA con el copy premium completo que acabas de presentar. " +
    "PROHIBIDO: volver a preguntar, pedir otra confirmación o decir publicado sin invocar la herramienta."
  );
}
