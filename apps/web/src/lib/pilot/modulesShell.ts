import { getPilotVisibleModules } from "@/modules/registry";

/**
 * Shell visible when ?modulesShell=pilot OR any registered module pilot is on
 * (e.g. ?viabilityModule=pilot or ?trendsModule=pilot).
 */
export function isModulesShellPilot(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const shell = params.get("modulesShell")?.trim().toLowerCase();
    if (shell === "pilot" || shell === "1" || shell === "true") return true;
    if (shell === "off" || shell === "prod" || shell === "production") {
      return false;
    }
  }
  if (process.env.NEXT_PUBLIC_MODULES_SHELL_PILOT === "true") return true;
  try {
    return getPilotVisibleModules().length > 0;
  } catch {
    return false;
  }
}
