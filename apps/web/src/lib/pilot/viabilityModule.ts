/** Piloto módulo viabilidad — activar con ?viabilityModule=pilot */

export function isViabilityModulePilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const pilot = params.get("viabilityModule")?.trim().toLowerCase();
    if (pilot === "pilot" || pilot === "1" || pilot === "true") return true;
    if (pilot === "off" || pilot === "prod" || pilot === "production") return false;
  }
  return process.env.NEXT_PUBLIC_VIABILITY_MODULE_PILOT === "true";
}

export const VIABILITY_PILOT_HEADER = "X-CED-Viability-Pilot";
export const VIABILITY_PILOT_HEADER_VALUE = "1";
