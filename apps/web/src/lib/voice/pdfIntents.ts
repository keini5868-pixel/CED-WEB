/** Intents para generar PDF por voz (fallback si el modelo no invoca generar_pdf). */

const PDF_INTENT_PATTERNS = [
  /\b(genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|guárdame)\s+(?:un(?:a)?\s+)?pdf\b/i,
  /\bpdf\s+(?:de|con|sobre)\b/i,
  /\b(?:haz|hazme)\s+(?:un(?:a)?\s+)?pdf\b/i,
];

export function isPdfIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 8) return false;
  return PDF_INTENT_PATTERNS.some((p) => p.test(t));
}

export function parsePdfRequest(text: string): { title: string; content: string } | null {
  const t = text.trim();
  if (!isPdfIntent(t)) return null;

  const titleMatch = t.match(
    /(?:t[ií]tulo|titulo)\s*[:.]?\s*["']?([^"'\n.]+?)["']?(?:\s+(?:contenido|sobre|de|con)\b|$)/i,
  );
  const contentMatch = t.match(
    /(?:contenido|sobre|de|con|que\s+diga|que\s+incluya)\s*[:.]?\s*(.+)$/is,
  );

  let title = titleMatch?.[1]?.trim() || "Documento CED";
  let content = contentMatch?.[1]?.trim() || "";

  if (!content) {
    content = t
      .replace(
        /^(?:genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|guárdame|haz|hazme)\s+(?:un(?:a)?\s+)?pdf\s*(?:de|con|sobre)?\s*/i,
        "",
      )
      .trim();
  }

  if (!content || content.length < 3) {
    content = title !== "Documento CED" ? title : t;
  }

  title = title.slice(0, 200);
  content = content.slice(0, 12000);

  return { title, content };
}
