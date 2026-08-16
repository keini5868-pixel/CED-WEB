/** Eventos de chrome HUD — el hub de voz escucha; el header no monta la sesión. */

export const CED_OPEN_SETTINGS_EVENT = "ced-open-settings";
export const CED_OPEN_CHAT_EVENT = "ced-open-chat";
export const CED_OPEN_ADVANCED_EVENT = "ced-open-advanced";
export const CED_OPEN_FINANCE_EVENT = "ced-open-finance";

export function dispatchCedOpenSettings(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CED_OPEN_SETTINGS_EVENT));
}

export function dispatchCedOpenModule(moduleId: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("ced-open-module", { detail: { module: moduleId } }),
  );
}

export function isDashboardPath(pathname: string | null | undefined): boolean {
  const p = (pathname || "").replace(/\/$/, "") || "/";
  return p === "/dashboard" || p === "/app" || p === "/dev/hud-preview";
}
