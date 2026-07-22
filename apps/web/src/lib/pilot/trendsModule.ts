/** Piloto módulo tendencias — activar con ?trendsModule=pilot */

export function isTrendsModulePilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const pilot = params.get("trendsModule")?.trim().toLowerCase();
    if (pilot === "pilot" || pilot === "1" || pilot === "true") return true;
    if (pilot === "off" || pilot === "prod" || pilot === "production") return false;
  }
  return process.env.NEXT_PUBLIC_TRENDS_MODULE_PILOT === "true";
}

export const TRENDS_PILOT_HEADER = "X-CED-Trends-Pilot";
export const TRENDS_PILOT_HEADER_VALUE = "1";
