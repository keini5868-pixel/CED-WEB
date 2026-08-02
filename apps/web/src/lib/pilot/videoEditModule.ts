/**
 * Módulo Video Edit — piloto aislado.
 * Visible solo con ?videoEditModule=pilot|1|true
 * o NEXT_PUBLIC_VIDEO_EDIT_MODULE_PILOT=true.
 * Kill-switch: ?videoEditModule=off | env !== "true".
 */

export const VIDEO_EDIT_PILOT_HEADER = "X-CED-Video-Edit-Pilot";
export const VIDEO_EDIT_PILOT_HEADER_VALUE = "1";

export function isVideoEditModulePilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const flag = params.get("videoEditModule")?.trim().toLowerCase();
    if (flag === "off" || flag === "false" || flag === "0" || flag === "prod") {
      return false;
    }
    if (flag === "pilot" || flag === "1" || flag === "true" || flag === "on") {
      return true;
    }
  }
  return process.env.NEXT_PUBLIC_VIDEO_EDIT_MODULE_PILOT === "true";
}
