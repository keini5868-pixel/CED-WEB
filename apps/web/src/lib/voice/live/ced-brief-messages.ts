/** Instrucciones de voz CED — una sola utterance, sin prefijos duplicados. */

import type { UserAddressContext } from "@/lib/api/profile";

export function cedGreetingTurn(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<UserAddressContext, "greetingPhraseJarvis" | "greetingPhraseStandard"> | null,
): string {
  const phrase =
    voiceProfile === "jarvis"
      ? address?.greetingPhraseJarvis || "Buenas tardes. ¿En qué puedo asistirle hoy?"
      : address?.greetingPhraseStandard || "Hola. ¿Cómo va todo?";
  return (
    "[CED_GREETING] Di EXACTAMENTE esta frase una sola vez, sin añadir nada antes ni después: " +
    `"${phrase}"`
  );
}

export function cedBriefTurn(spoken: string): string {
  const body = spoken.trim();
  return (
    "[CED_BRIEF] Lee en voz alta UNA sola vez el siguiente texto. " +
    "PROHIBIDO: muletillas previas (claro, perfecto, dale, listo, ok). " +
    "PROHIBIDO: repetir la misma idea dos veces.\n\n" +
    body
  );
}

export function cedSearchStatusTurn(): string {
  return cedBriefTurn("Indícame qué quieres buscar y lo consulto en internet.");
}
