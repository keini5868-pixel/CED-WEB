/**
 * Módulo Tendencias — producción.
 * Visible para usuarios logueados salvo kill-switch NEXT_PUBLIC_TRENDS_MODULE_ENABLED=false
 * (el API también respeta TRENDS_MODULE_ENABLED).
 */

export function isTrendsModuleEnabled(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const forceOff = params.get("trendsModule")?.trim().toLowerCase();
    // Escape hatch local: ?trendsModule=off (no reintroduce el flag pilot)
    if (forceOff === "off" || forceOff === "false" || forceOff === "0") {
      return false;
    }
  }
  const env = process.env.NEXT_PUBLIC_TRENDS_MODULE_ENABLED;
  if (env === "false" || env === "0" || env === "off") return false;
  return true;
}

/** @deprecated use isTrendsModuleEnabled */
export function isTrendsModulePilot(): boolean {
  return isTrendsModuleEnabled();
}
