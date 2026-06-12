/** Instrucciones de voz CED — una sola utterance, sin prefijos duplicados. */

export function cedGreetingTurn(voiceProfile: "standard" | "jarvis" = "jarvis"): string {
  const phrase =
    voiceProfile === "jarvis"
      ? "Buenos días, Keini. ¿En qué trabajamos hoy?"
      : "Hola Keini. ¿Cómo va todo?";
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
