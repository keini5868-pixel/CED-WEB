/** Instrucciones de voz CED — una sola utterance, sin prefijos duplicados. */

import type { UserAddressContext } from "@/lib/api/profile";

function timeOfDaySalutation(): string {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return "Buenos días";
  if (hour >= 12 && hour < 19) return "Buenas tardes";
  return "Buenas noches";
}

function resolveHonorific(
  address?: Pick<UserAddressContext, "honorific" | "gender" | "displayName" | "firstName"> | null,
): string {
  const h = address?.honorific?.trim();
  if (h) return h;
  if (address?.gender === "female") return "Señora";
  if (address?.gender === "male") return "Señor";
  return address?.displayName?.trim() || address?.firstName?.trim() || "";
}

/** Saludo recepción Jarvis — hora local + tratamiento por género. */
export function cedReceptionGreetingPhrase(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<
    UserAddressContext,
    "honorific" | "gender" | "displayName" | "firstName" | "greetingPhraseJarvis" | "greetingPhraseStandard"
  > | null,
): string {
  if (voiceProfile !== "jarvis") {
    return address?.greetingPhraseStandard || "Hola. ¿En qué trabajamos?";
  }
  const tod = timeOfDaySalutation();
  const title = resolveHonorific(address);
  if (title === "Señor" || title === "Señora" || title === "Don" || title === "Doña") {
    return (
      `Hola, ${title}. ¿Cómo está? ${tod}. ` +
      "Estoy aquí para servirle. ¿Cuáles son los planes para hoy?"
    );
  }
  const name = title || "Usuario";
  return (
    `Hola, ${name}. ¿Cómo está? ${tod}. ` +
    "Estoy aquí para servirle. ¿Cuáles son los planes para hoy?"
  );
}

/** @deprecated Usar cedReceptionGreetingPhrase */
export function cedGreetingPhrase(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<UserAddressContext, "greetingPhraseJarvis" | "greetingPhraseStandard"> | null,
): string {
  return cedReceptionGreetingPhrase(voiceProfile, address);
}

export function cedGreetingBriefTurn(phrase: string): string {
  const body = phrase.trim();
  return (
    "[CED_GREETING] Lee en voz alta UNA sola vez, de corrido y sin pausas largas, el texto siguiente. " +
    "PROHIBIDO: dividir en dos respuestas, cambiar palabras, añadir frases ni listar capacidades.\n\n" +
    body
  );
}

/** Presencia tras silencio prolongado — una sola frase. */
export function cedIdlePresencePhrase(
  address?: Pick<UserAddressContext, "honorific" | "gender"> | null,
): string {
  const title = resolveHonorific(address);
  if (title === "Señor" || title === "Señora" || title === "Don" || title === "Doña") {
    return `${title}, sigo aquí.`;
  }
  return "Sigo aquí.";
}

/** @deprecated Usar cedGreetingBriefTurn + cedReceptionGreetingPhrase */
export function cedGreetingTurn(
  voiceProfile: "standard" | "jarvis" = "jarvis",
  address?: Pick<UserAddressContext, "greetingPhraseJarvis" | "greetingPhraseStandard"> | null,
): string {
  return cedGreetingBriefTurn(cedReceptionGreetingPhrase(voiceProfile, address));
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
  const net = platform === "facebook" ? "Facebook" : "Instagram";
  return (
    "[CED_PUBLISH] El usuario confirmó. Invoca " +
    tool +
    " AHORA con el copy completo. " +
    "Antes: 'Procediendo con la publicación'. " +
    "Después de ejecutar: confirma en voz 'Publicación enviada con éxito a " +
    net +
    "'. " +
    "PROHIBIDO: 'Va', 'Va para', 'Ok', 'Listo', volver a preguntar o quedarse en silencio tras publicar."
  );
}

function honorificSuffix(
  address?: Pick<UserAddressContext, "honorific"> | null,
): string {
  const h = address?.honorific?.trim();
  return h ? `, ${h}` : "";
}

/** Confirmación Jarvis tras publicar con éxito. */
export function cedPublishSuccessPhrase(
  platform: "facebook" | "instagram",
  address?: Pick<UserAddressContext, "honorific"> | null,
): string {
  const net = platform === "facebook" ? "Facebook" : "Instagram";
  return `Publicación enviada con éxito a ${net}${honorificSuffix(address)}.`;
}

/** Error Jarvis tras fallo de publicación. */
export function cedPublishFailurePhrase(
  reason: string,
  address?: Pick<UserAddressContext, "honorific"> | null,
): string {
  const detail = reason.trim() || "no fue posible completar la publicación";
  return `Lamentablemente ${detail}${honorificSuffix(address)}.`;
}
