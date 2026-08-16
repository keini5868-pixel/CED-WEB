/** Eventos de chrome HUD — el hub de voz escucha; el header no monta la sesión. */

export const CED_OPEN_SETTINGS_EVENT = "ced-open-settings";
export const CED_OPEN_CHAT_EVENT = "ced-open-chat";
export const CED_OPEN_ADVANCED_EVENT = "ced-open-advanced";
export const CED_OPEN_FINANCE_EVENT = "ced-open-finance";

export function dispatchCedOpenSettings(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CED_OPEN_SETTINGS_EVENT));
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
