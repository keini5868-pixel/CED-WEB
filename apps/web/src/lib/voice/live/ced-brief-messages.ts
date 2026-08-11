/** Instrucciones de voz CED — una sola utterance, sin prefijos duplicados. */

import type { VoiceProfileId } from "@ced/types";
import type { UserAddressContext } from "@/lib/api/profile";

type CedGreetingAddress = Partial<
  Pick<
    UserAddressContext,
    | "honorific"
    | "gender"
    | "displayName"
    | "firstName"
    | "greetingPhraseJarvis"
    | "greetingPhraseStandard"
  >
> | null;


function isInvalidHonorific(raw: string): boolean {
  const h = raw.trim().toLowerCase().replace(/\./g, "");
  return h.length < 3 || /^(si|sí|sir|yes|ok|va|si senor|si señor)$/.test(h);
}

export function cedResolveHonorific(
  address?: CedGreetingAddress,
): string {
  const h = address?.honorific?.trim();
  if (h && !isInvalidHonorific(h)) {
    if (h === "Señor" || h === "Señora" || h === "Don" || h === "Doña") return h;
    if (/^(senor|señor)$/i.test(h)) return "Señor";
    if (/^(senora|señora)$/i.test(h)) return "Señora";
    return h;
  }
  if (address?.gender === "female") return "Señora";
  if (address?.gender === "male") return "Señor";
  const name = address?.displayName?.trim() || address?.firstName?.trim() || "";
  if (name && !isInvalidHonorific(name)) return name;
  return "Señor";
}

/** Saludo fijo — Señor/Señora + en qué puedo ayudarle hoy. */
export function cedReceptionGreetingPhrase(
  voiceProfile: VoiceProfileId = "jarvis",
  address?: CedGreetingAddress,
): string {
  if (voiceProfile !== "jarvis") {
    return address?.greetingPhraseStandard || "Hola. ¿En qué trabajamos?";
  }
  const title = cedResolveHonorific(address);
  if (title === "Señor" || title === "Señora" || title === "Don" || title === "Doña") {
    return `A su servicio, ${title}.`;
  }
  const name = title || "Usuario";
  return `Hola, ${name}. ¿En qué puedo ayudarle hoy?`;
}

/** @deprecated Usar cedReceptionGreetingPhrase */
export function cedGreetingPhrase(
  voiceProfile: VoiceProfileId = "jarvis",
  address?: CedGreetingAddress,
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

/** Tras silencio — una sola frase de presencia. */
export function cedIdlePresencePhrase(
  address?: CedGreetingAddress,
): string {
  const title = cedResolveHonorific(address);
  if (title === "Señor" || title === "Señora" || title === "Don" || title === "Doña") {
    return `¿Está ahí, ${title}?`;
  }
  return "¿Está ahí?";
}

/** @deprecated Usar cedGreetingBriefTurn + cedReceptionGreetingPhrase */
export function cedGreetingTurn(
  voiceProfile: VoiceProfileId = "jarvis",
  address?: CedGreetingAddress,
): string {
  return cedGreetingBriefTurn(cedReceptionGreetingPhrase(voiceProfile, address));
}

export function cedBriefTurn(spoken: string): string {
  const body = spoken.trim();
  return (
    "[CED_BRIEF] Lee en voz alta UNA sola vez el siguiente texto. " +
    "PROHIBIDO: muletillas previas (claro, perfecto, dale, listo, ok). " +
    "PROHIBIDO: saludar, decir hola, 'muy buenas', '¿en qué puedo ayudarle?'. " +
    "PROHIBIDO: repetir la misma idea dos veces.\n\n" +
    body
  );
}

/** Guion / análisis avanzado — lectura larga, una sola voz. */
export function cedAdvancedBriefTurn(spoken: string): string {
  const body = spoken.trim();
  return (
    "[CED_BRIEF] Lee en voz UNA sola vez, de corrido, el guion o análisis siguiente. " +
    "PROHIBIDO: saludar, volver a saludar, 'muy buenas', preguntar '¿en qué te ayudo?'. " +
    "PROHIBIDO: resumir u omitir párrafos — lee el texto completo que sigue.\n\n" +
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
  address?: Pick<UserAddressContext, "honorific" | "gender"> | null,
): string {
  const h = cedResolveHonorific(address);
  return `, ${h}`;
}

/** Confirmación Jarvis tras publicar con éxito. */
export function cedPublishSuccessPhrase(
  _platform: "facebook" | "instagram",
  address?: Pick<UserAddressContext, "honorific" | "gender"> | null,
): string {
  const h = cedResolveHonorific(address);
  return `Publicación enviada, ${h}. ¿Algo más en lo que pueda servirle?`;
}

/** Error Jarvis tras fallo de publicación. */
export function cedPublishFailurePhrase(
  reason: string,
  address?: Pick<UserAddressContext, "honorific" | "gender"> | null,
): string {
  const detail = reason.trim() || "no fue posible completar la publicación";
  return `Lamentablemente ${detail}${honorificSuffix(address)}.`;
}
