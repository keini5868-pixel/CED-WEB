/**
 * Módulo Automatización — piloto aislado.
 * Visible con ?automationModule=pilot|1|true
 * o NEXT_PUBLIC_AUTOMATION_MODULE_ENABLED=true.
 * Kill-switch: ?automationModule=off.
 */

export const AUTOMATION_PILOT_HEADER = "X-CED-Automation-Pilot";
export const AUTOMATION_PILOT_HEADER_VALUE = "1";

export function isAutomationModulePilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const flag = params.get("automationModule")?.trim().toLowerCase();
    if (flag === "off" || flag === "false" || flag === "0" || flag === "prod") {
      return false;
    }
    if (flag === "pilot" || flag === "1" || flag === "true" || flag === "on") {
      return true;
    }
  }
  return process.env.NEXT_PUBLIC_AUTOMATION_MODULE_ENABLED === "true";
}
