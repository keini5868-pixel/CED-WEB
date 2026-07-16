/** Intents para generar PDF por voz (fallback si el modelo no invoca generar_pdf). */

const PDF_INTENT_PATTERNS = [
  // NO usar solo /\bpdf\b/ — dispara falsos positivos en listas de capacidades.
  /\b(genera|generar|gener[aá]me|crea|crear|cr[eé]ame|exporta|exportar|convierte|convertir|guarda|guárdame|dame|pon|pásalo|pasalo)\s+(?:.{0,48}?\s+)?(?:en\s+)?(?:un(?:a)?\s+)?pdf\b/i,
  /\b(?:esto|lo|la\s+informaci[oó]n|el\s+plan|la\s+estrategia)\s+(?:en\s+)?(?:un(?:a)?\s+)?pdf\b/i,
  /\bpdf\s+(?:de|con|sobre)\b/i,
  /\b(?:haz|hazme)\s+(?:un(?:a)?\s+)?pdf\b/i,
  /\b(?:en|como)\s+(?:un(?:a)?\s+)?pdf\b/i,
];

export function isPdfIntent(text: string): boolean {
  const t = text.trim();
  if (t.length < 6) return false;
  return PDF_INTENT_PATTERNS.some((p) => p.test(t));
}

const PDF_THIS_REF =
  /\b(esto|lo|la\s+informaci[oó]n|esa\s+informaci[oó]n|con\s+eso|lo\s+anterior|el\s+plan|la\s+estrategia|ese\s+plan|el\s+documento|aqu[ií]\s+(?:presentado|mostrado))\b/i;

function inferPdfTitle(userText: string, content: string): string {
  const blob = `${userText}\n${content.slice(0, 900)}`;
  if (/plan\s+semanal|estrategia\s+semanal/i.test(blob)) return "Plan Semanal de Estrategia CED";
  if (/lanzamiento\s+(?:de\s+)?ced/i.test(blob)) return "Plan de Lanzamiento CED";
  if (/\bestrategia\b/i.test(blob) && !/tornado|noticia/i.test(blob)) return "Estrategia CED";
  if (/\btornado\b/i.test(blob)) {
    if (/\bchina\b|\bhubei\b/i.test(blob)) return "Tornado EF2 en Hubei, China";
    return "Informe sobre Tornado";
  }
  const body = content.trim();
  for (const rawLine of body.split(/[\n.!?]+/)) {
    let line = rawLine.trim();
    line = line.replace(/^(?:señor,?\s*)?(?:sobre su consulta:?\s*)?/i, "").trim();
    if (line.length >= 18 && line.length <= 110 && !/^(?:un momento|consulto|pdf)\b/i.test(line)) {
      return line.slice(0, 120);
    }
  }
  return "Documento CED";
}

export function parsePdfRequest(
  text: string,
  recentAssistantTexts: string[] = [],
): { title: string; content: string } | null {
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
        /^(?:genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|guárdame|haz|hazme|dame|pon|pásalo|pasalo)\s+(?:.{0,48}?\s+)?(?:en\s+)?(?:un(?:a)?\s+)?pdf\s*(?:de|con|sobre)?\s*/i,
        "",
      )
      .trim();
  }

  const pasted = t.match(/(?:en\s+)?(?:un(?:a)?\s+)?pdf\s*\n?\s*(.+)$/is);
  const pastedBody = pasted?.[1]?.trim() ?? "";
  if (pastedBody.length >= 80) {
    content = pastedBody;
  }

  if (content.length < 200 && PDF_THIS_REF.test(t)) {
    const previous = [...recentAssistantTexts].reverse().find((msg) => msg.trim().length >= 120);
    if (previous) content = previous.trim();
  }

  if (!content || content.length < 40) {
    const previous = [...recentAssistantTexts].reverse().find((msg) => msg.trim().length >= 80);
    if (previous) content = previous.trim();
  }

  if (title === "Documento CED" || title.length < 8) {
    title = inferPdfTitle(t, content);
  }

  if (!content || content.length < 3) {
    content = title !== "Documento CED" ? title : t;
  }

  title = title.slice(0, 200);
  content = content.slice(0, 12000);

  return { title, content };
}
