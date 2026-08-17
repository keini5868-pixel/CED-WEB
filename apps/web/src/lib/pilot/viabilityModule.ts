/**
 * Módulo Análisis de Producto — producción.
 * Visible para usuarios logueados salvo kill-switch NEXT_PUBLIC_VIABILITY_MODULE_ENABLED=false
 * (el API también respeta VIABILITY_MODULE_ENABLED).
 */

export function isViabilityModuleEnabled(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const forceOff = params.get("viabilityModule")?.trim().toLowerCase();
    // Escape hatch local: ?viabilityModule=off (no reintroduce el flag pilot)
    if (forceOff === "off" || forceOff === "false" || forceOff === "0") {
      return false;
    }
  }
  const env = process.env.NEXT_PUBLIC_VIABILITY_MODULE_ENABLED;
  if (env === "false" || env === "0" || env === "off") return false;
  return true;
}

/** @deprecated use isViabilityModuleEnabled */
export function isViabilityModulePilot(): boolean {
  return isViabilityModuleEnabled();
}
