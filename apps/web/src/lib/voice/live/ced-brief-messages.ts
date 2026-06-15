/** Instrucciones de voz CED — una sola utterance, sin prefijos duplicados. */

import type { UserAddressContext } from "@/lib/api/profile";

export function cedGreetingTurn(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<UserAddressContext, "greetingPhraseJarvis" | "greetingPhraseStandard"> | null,
): string {
  const phrase =
    voiceProfile === "jarvis"
      ? address?.greetingPhraseJarvis || "Hola. ¿En qué trabajamos?"
      : address?.greetingPhraseStandard || "Hola. ¿En qué trabajamos?";
  return (
    "[CED_GREETING] Di EXACTAMENTE esta frase una sola vez, sin añadir nada antes ni después: " +
    `"${phrase}"` +
    " PROHIBIDO: segunda frase, listar capacidades, mencionar ventas/prospección, " +
    "preguntar qué quieres mejorar, o seguir hablando si el usuario no responde."
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
