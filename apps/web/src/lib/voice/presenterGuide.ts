/** Guía del holograma: abre o cierra cualquier zona de la que hables. */

import { runPresenterClosers } from "./presenterCloseBus";

export type GuideAction = "close-all" | "close-module" | "close-workspace" | "escape";

export type GuideStep = {
  hotspot?: string;
  click?: boolean;
  force?: "open" | "close";
  action?: GuideAction;
};

type Rule = {
  re: RegExp;
  steps: GuideStep[];
};

const CLOSE_RULES: Rule[] = [
  {
    re: /\b(sistema|men[uú]|pesta[nñ]a)\b/i,
    steps: [{ action: "close-all" }],
  },
  {
    re: /\b(avanzado)\b/i,
    steps: [{ action: "close-workspace" }],
  },
  {
    re: /\b(finanzas|finance)\b/i,
    steps: [{ action: "close-workspace" }],
  },
  {
    re: /\b(c[aá]mara|camara)\b/i,
    steps: [{ hotspot: "camara", click: true, force: "close" }],
  },
  {
    re: /\b(configuraci[oó]n|ajustes|settings)\b/i,
    steps: [{ action: "escape" }],
  },
  {
    re: /\b(oportunidad(?:es)?(?:\s+(?:pm|p\.?\s*m\.?))?|fitline|fit\s*line)\b/i,
    steps: [{ hotspot: "module-close", click: true, force: "close" }, { action: "close-module" }],
  },
  {
    re: /\b(producto|viabilidad|tendencia|video|automatizaci[oó]n|m[oó]dulo)\b/i,
    steps: [{ hotspot: "module-close", click: true, force: "close" }, { action: "close-module" }],
  },
  {
    re: /\b(estructura(?:\s+pm)?|equipo)\b/i,
    steps: [{ action: "close-all" }],
  },
  {
    re: /\b(mapa)\b/i,
    steps: [{ action: "escape" }],
  },
];

const OPEN_RULES: Rule[] = [
  {
    re: /\b(whats\s*app|wasap)\b/i,
    steps: [
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-whatsapp", click: true },
    ],
  },
  {
    re: /\bpapelera\b/i,
    steps: [
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-trash", click: true },
    ],
  },
  {
    re: /\b(historial|archivos|im[aá]genes y pdf)\b/i,
    steps: [
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-history", click: true },
    ],
  },
  {
    re: /\b(planes?|suscripci[oó]n|membres[ií]a)\b/i,
    steps: [
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-plans", click: true },
    ],
  },
  {
    re: /\b(cuentas?|mi cuenta|perfil)\b/i,
    steps: [
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-account", click: true },
    ],
  },
  {
    re: /\b(configuraci[oó]n|ajustes|settings)\b/i,
    steps: [
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-settings", click: true },
    ],
  },
  {
    re: /\b(conectar redes|redes sociales|instagram|facebook)\b/i,
    steps: [{ hotspot: "redes", click: true }],
  },
  {
    re: /\b(oportunidad(?:es)?(?:\s+(?:pm|p\.?\s*m\.?))?|fitline|fit\s*line|opps)\b/i,
    steps: [{ hotspot: "opportunities", click: true }],
  },
  {
    re: /\b(producto|viabilidad|an[aá]lisis de producto)\b/i,
    steps: [{ hotspot: "viability", click: true }],
  },
  {
    re: /\b(tendencia|tendencias|an[aá]lisis de tendencia)\b/i,
    steps: [{ hotspot: "trends", click: true }],
  },
  {
    re: /\b(estructura(?:\s+pm)?|equipo)\b/i,
    steps: [{ hotspot: "team", click: true }],
  },
  {
    re: /\b(edici[oó]n de video|editar video)\b/i,
    steps: [{ hotspot: "video-edit", click: true }],
  },
  {
    re: /\b(automatizaci[oó]n|automation)\b/i,
    steps: [{ hotspot: "automation", click: true }],
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
    re: /\b(men[uú]|pesta[nñ]a|sistema)\b/i,
    steps: [{ hotspot: "sistema", click: true, force: "open" }],
  },
];

const CLOSE_VERB =
  String.raw`(?:cierra|cerrar|cierre|cierr[oa]|ciera|sierra|serrar|ci[eé]rrame|ci[eé]rralo|ci[eé]rrala|oculta|quita(?:le)?)`;

function isCloseIntent(text: string): boolean {
  return new RegExp(String.raw`\b${CLOSE_VERB}\b`, "i").test(text);
}

export function isPresenterCloseSpeech(text: string): boolean {
  const t = (text || "").trim();
  return isCloseIntent(t) || isCloseAll(t);
}

export function isCloseAllGuide(steps: GuideStep[]): boolean {
  return steps.length === 1 && steps[0]?.action === "close-all";
}

function isCloseAll(text: string): boolean {
  return (
    new RegExp(String.raw`^(?:${CLOSE_VERB})(?:\s+todo)?[\s!.]*$`, "i").test(text) ||
    new RegExp(
      String.raw`\b${CLOSE_VERB}\s+(?:todo|eso|esto|esa|ese|el\s+panel|las?\s+pesta[nñ]as?|lo que)\b`,
      "i",
    ).test(text) ||
    /\b(?:vuelve|volver|regresa|atr[aá]s)\s+(?:al\s+)?(?:dashboard|inicio|chat)?\b/i.test(text)
  );
}

export function matchPresenterGuide(text: string): GuideStep[] | null {
  const t = (text || "").trim();
  if (t.length < 3) return null;
  if (isCloseAll(t)) return [{ action: "close-all" }];
  if (isCloseIntent(t)) {
    for (const rule of CLOSE_RULES) {
      if (rule.re.test(t)) return rule.steps;
    }
    return [{ action: "close-all" }];
  }
  for (const rule of OPEN_RULES) {
    if (rule.re.test(t)) return rule.steps;
  }
  return null;
}

export function queryHotspot(id: string): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>(`[data-ced-hotspot="${id}"]`);
}

/** Clic nativo: .click() a veces no dispara el onClick de un menú / overlay. */
/** Un solo clic nativo. No despachar click + el.click(): en botones toggle se anulan. */
export function clickElement(el: HTMLElement): void {
  el.click();
}

export function closeTargetHotspot(): HTMLElement | null {
  const moduleClose = queryHotspot("module-close");
  if (moduleClose) return moduleClose;
  const sys = queryHotspot("sistema");
  if (sys?.getAttribute("aria-expanded") === "true") return sys;
  return queryHotspot("home") || sys;
}

export function runPresenterAction(action: GuideAction): void {
  if (typeof window === "undefined") return;
  runPresenterClosers();
  if (action === "close-module" || action === "close-all") {
    window.dispatchEvent(new Event("ced-close-module"));
    const closer = queryHotspot("module-close");
    if (closer) clickElement(closer);
  }
  if (action === "close-workspace" || action === "close-all") {
    window.dispatchEvent(new Event("ced-close-workspace"));
  }
  if (action === "escape" || action === "close-all") {
    window.dispatchEvent(new Event("ced-close-settings"));
    window.dispatchEvent(new Event("ced-close-map"));
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }),
    );
  }
  if (action === "close-all") {
    window.dispatchEvent(new Event("ced-close-hud-menus"));
    const cam = queryHotspot("camara");
    if (cam?.getAttribute("data-ced-open") === "true") clickElement(cam);
    window.dispatchEvent(new Event("ced-go-dashboard"));
  }
}
