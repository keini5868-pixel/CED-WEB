/** Guía del holograma: qué zona abrir según lo que el presentador dice. */

export type GuideStep = {
  hotspot: string;
  click: boolean;
};

type Rule = {
  re: RegExp;
  steps: GuideStep[];
};

const RULES: Rule[] = [
  {
    re: /\b(whats\s*app|wasap)\b/i,
    steps: [
      { hotspot: "sistema", click: true },
      { hotspot: "nav-whatsapp", click: true },
    ],
  },
  {
    re: /\bpapelera\b/i,
    steps: [
      { hotspot: "sistema", click: true },
      { hotspot: "nav-trash", click: true },
    ],
  },
  {
    re: /\b(historial|archivos|im[aá]genes y pdf)\b/i,
    steps: [
      { hotspot: "sistema", click: true },
      { hotspot: "nav-history", click: true },
    ],
  },
  {
    re: /\b(planes?|suscripci[oó]n|membres[ií]a)\b/i,
    steps: [
      { hotspot: "sistema", click: true },
      { hotspot: "nav-plans", click: true },
    ],
  },
  {
    re: /\b(cuentas?|mi cuenta|perfil)\b/i,
    steps: [
      { hotspot: "sistema", click: true },
      { hotspot: "nav-account", click: true },
    ],
  },
  {
    re: /\b(configuraci[oó]n|ajustes|settings)\b/i,
    steps: [
      { hotspot: "sistema", click: true },
      { hotspot: "nav-settings", click: true },
    ],
  },
  {
    re: /\b(conectar redes|redes sociales|instagram|facebook)\b/i,
    steps: [{ hotspot: "redes", click: true }],
  },
  {
    re: /\b(oportunidades|fitline|fit\s*line|opps)\b/i,
    steps: [{ hotspot: "opportunities", click: true }],
  },
  {
    re: /\b(producto|viabilidad)\b/i,
    steps: [{ hotspot: "viability", click: true }],
  },
  {
    re: /\b(tendencia|tendencias)\b/i,
    steps: [{ hotspot: "trends", click: true }],
  },
  {
    re: /\b(estructura|equipo)\b/i,
    steps: [{ hotspot: "team", click: true }],
  },
  {
    re: /\b(edici[oó]n de video|editar video)\b/i,
    steps: [{ hotspot: "video-edit", click: true }],
  },
  {
    re: /\bavanzado\b/i,
    steps: [{ hotspot: "avanzado", click: true }],
  },
  {
    re: /\b(finanzas|finance)\b/i,
    steps: [{ hotspot: "finanzas", click: true }],
  },
  {
    re: /\b(c[aá]mara|camara)\b/i,
    steps: [{ hotspot: "camara", click: true }],
  },
  {
    re: /\b(mapa|navegaci[oó]n)\b/i,
    steps: [{ hotspot: "mapa", click: true }],
  },
  {
    re: /\b(chat|escribe|escribime)\b/i,
    steps: [{ hotspot: "chat", click: false }],
  },
  {
    re: /\basistente\b/i,
    steps: [{ hotspot: "asistente", click: false }],
  },
  {
    re: /\bsistema\b/i,
    steps: [{ hotspot: "sistema", click: true }],
  },
];

export function matchPresenterGuide(text: string): GuideStep[] | null {
  const t = (text || "").trim();
  if (t.length < 3) return null;
  for (const rule of RULES) {
    if (rule.re.test(t)) return rule.steps;
  }
  return null;
}

export function queryHotspot(id: string): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>(`[data-ced-hotspot="${id}"]`);
}
