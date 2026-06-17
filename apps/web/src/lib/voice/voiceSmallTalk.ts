/** Saludos casuales — no disparan herramientas ni monólogos del modelo. */

export function isCasualSocialGreeting(text: string): boolean {
  const t = text.trim();
  if (t.length < 5 || t.length > 96) return false;
  const low = t.toLowerCase();
  const greeting =
    /\b(hola|buenos|buenas|hey|qu[eé] tal|buen d[ií]a|buenas tardes|buenas noches)\b/i.test(
      low,
    );
  const smallTalk =
    /\b(c[oó]mo est[aá]s|qu[eé] tal|c[oó]mo te va|todo bien|zeke|zed|ced)\b/i.test(
      low,
    );
  if (!greeting && !smallTalk) return false;
  if (
    /\b(comentario|instagram|facebook|prospecci|publicar|busca|clima|activa|necesito|quiero que|dime si|pdf|imagen|c[aá]mara|protecci|transpos)\b/i.test(
      low,
    )
  ) {
    return false;
  }
  return true;
}

/** Solo "Señor." / "Señora." como preferencia explícita. */
export function isStandaloneHonorificPreference(text: string): boolean {
  return /^se[nñ]or[a]?[.!?,]*$/i.test(text.trim());
}
