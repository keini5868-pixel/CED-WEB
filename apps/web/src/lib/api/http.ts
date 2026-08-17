/** Parsea respuesta JSON; detecta HTML (API mal configurada). */
export async function parseApiJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  const trimmed = text.trim();
  if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
    throw new Error(
      "La API no responde. Intente de nuevo en un momento.",
    );
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(
      trimmed.slice(0, 120) || "Respuesta inválida del servidor",
    );
  }
}
