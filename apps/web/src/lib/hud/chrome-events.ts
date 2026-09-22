/** Eventos de chrome HUD — el hub de voz escucha; el header no monta la sesión. */

export const CED_OPEN_SETTINGS_EVENT = "ced-open-settings";
export const CED_OPEN_HISTORY_EVENT = "ced-open-history";
export const CED_OPEN_CHAT_EVENT = "ced-open-chat";
export const CED_OPEN_ADVANCED_EVENT = "ced-open-advanced";
export const CED_OPEN_FINANCE_EVENT = "ced-open-finance";

export function dispatchCedOpenSettings(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CED_OPEN_SETTINGS_EVENT));
}

export function dispatchCedOpenHistory(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CED_OPEN_HISTORY_EVENT));
}

export function dispatchCedOpenModule(
  moduleId: string,
  extra?: { opportunity_id?: string; highlight?: string },
): void {
  if (typeof window === "undefined") return;
  const opportunityId = extra?.opportunity_id?.trim();
  const highlight = extra?.highlight?.trim();
  if (moduleId === "opportunities" && (opportunityId || highlight)) {
    try {
      window.sessionStorage.setItem(
        "ced-opps-guide",
        JSON.stringify({
          opportunity_id: opportunityId || "fitline_pm",
          highlight: highlight || "signup",
        }),
      );
    } catch {
      /* ignore */
    }
  }
  window.dispatchEvent(
    new CustomEvent("ced-open-module", {
      detail: {
        module: moduleId,
        opportunity_id: opportunityId,
        highlight,
      },
    }),
  );
}

export type CedOpenModulePayload = {
  module?: string;
  opportunity_id?: string;
  highlight?: string;
};

export function applyCedOpenModule(
  payload?: CedOpenModulePayload | null,
): void {
  const moduleId = payload?.module?.trim();
  if (!moduleId) return;
  dispatchCedOpenModule(moduleId, {
    opportunity_id: payload?.opportunity_id,
    highlight: payload?.highlight,
  });
}

export const FITLINE_GUIDE_SEED =
  "modo guía: soy nuevo en FitLine, guíame desde cero";

export const CED_FITLINE_GUIDE_START_EVENT = "ced-fitline-guide-start";

export function startFitlineGuideFromHud(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CED_FITLINE_GUIDE_START_EVENT));
}

export const FITLINE_ENROLL_OPEN_MODULE = {
  module: "opportunities",
  opportunity_id: "fitline_pm",
  highlight: "signup",
} as const;

/** Pedido EXPLÍCITO de enlace PM / abrir OPPS — no copy, guion ni idea de contenido. */
export function wantsFitlineEnrollOpen(text: string): boolean {
  const t = (text || "").trim();
  if (t.length < 4) return false;
  const creative =
    /\b(?:gui[oó]n(?:es)?|guion(?:es)?|copy|copies|hook|gancho|reel|reels|caption|prompt|prompts|idea(?:s)?\s+de\s+(?:contenido|video|publicaci[oó]n)|secuencia\s+de\s+prospecci[oó]n)\b/i.test(
      t,
    );
  const abreOpps =
    /\b(?:puedes?|puedo|me\s+puedes?|podr[ií]as?)?\s*(?:abrir|abre(?:me)?|open)\s+(?:el\s+)?(?:m[oó]dulo\s+(?:de\s+)?|panel\s+(?:de\s+)?)?(?:opps|oportunidades)\b/i.test(
      t,
    );
  if (/(?:https?:\/\/)?(?:www\.)?pm-international\.com/i.test(t)) return true;
  if (abreOpps) return true;
  const hasLink =
    /\b(?:enlace|link|url|liga|hiperv[ií]nculo|p[aá]gina\s+web|sitio\s+web|web\s+oficial)\b/i.test(
      t,
    );
  const asked =
    /\b(?:dame|danos|p[aá]same|m[aá]ndame|env[ií]ame|necesito|quiero|cu[aá]l\s+es|d[oó]nde\s+(?:est[aá]|queda)|me\s+das|[aá]bre(?:me)?|abrir|open)\b/i.test(
      t,
    );
  const branded =
    /\b(?:fitline|fit\s*line|pm[\s-]?internationa[l]|pm[\s-]?internacional)\b/i.test(
      t,
    );
  const signup =
    /\b(?:inscripci[oó]n|inscribir(?:me|se)?|registro|registr(?:arme|arse)|unirme|patrocinio)\b/i.test(
      t,
    );
  const linkOfPm =
    /\b(?:enlace|link|url|liga)\s+(?:de\s+|del\s+|para\s+)?(?:pm(?:[\s-]?internationa[l])?|fitline|fit\s*line|inscripci[oó]n|registro|patrocinio)\b/i.test(
      t,
    );
  const notSignupLink =
    /\b(?:verificaci[oó]n|confirmar?\s+(?:el\s+)?correo|whatsapp|youtube|zoom|contrase[nñ]a|password)\b/i.test(
      t,
    );
  if (creative && !hasLink && !linkOfPm && !abreOpps) return false;
  if (notSignupLink && !signup) return false;
  if (linkOfPm) return true;
  if (hasLink && signup) return true;
  if (hasLink && branded && asked) return true;
  if (signup && branded && !creative) return true;
  return false;
}

export function openFitlineOppsIfRequested(text: string): boolean {
  if (!wantsFitlineEnrollOpen(text)) return false;
  const key = text.trim().toLowerCase();
  const now = Date.now();
  if (key === lastFitlineOppsOpenKey && now - lastFitlineOppsOpenAt < 8_000) {
    return true;
  }
  lastFitlineOppsOpenKey = key;
  lastFitlineOppsOpenAt = now;
  applyCedOpenModule(FITLINE_ENROLL_OPEN_MODULE);
  return true;
}

let lastFitlineOppsOpenKey = "";
let lastFitlineOppsOpenAt = 0;

export function consumeOppsGuide(): {
  opportunity_id: string;
  highlight: string;
} | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem("ced-opps-guide");
    if (!raw) return null;
    window.sessionStorage.removeItem("ced-opps-guide");
    const parsed = JSON.parse(raw) as {
      opportunity_id?: string;
      highlight?: string;
    };
    return {
      opportunity_id: parsed.opportunity_id || "fitline_pm",
      highlight: parsed.highlight || "signup",
    };
  } catch {
    return null;
  }
}

export function isDashboardPath(pathname: string | null | undefined): boolean {
  const p = (pathname || "").replace(/\/$/, "") || "/";
  return p === "/dashboard" || p === "/app" || p === "/dev/hud-preview";
}
