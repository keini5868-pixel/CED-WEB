/** Piloto módulo oportunidades — activar con ?opportunitiesModule=pilot */

export function isOpportunitiesModulePilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const pilot = params.get("opportunitiesModule")?.trim().toLowerCase();
    if (pilot === "pilot" || pilot === "1" || pilot === "true") return true;
    if (pilot === "off" || pilot === "prod" || pilot === "production") return false;
  }
  return process.env.NEXT_PUBLIC_OPPORTUNITIES_MODULE_PILOT === "true";
}

export const OPPORTUNITIES_PILOT_HEADER = "X-CED-Opportunities-Pilot";
export const OPPORTUNITIES_PILOT_HEADER_VALUE = "1";
