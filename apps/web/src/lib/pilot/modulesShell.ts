import { getVisibleModules } from "@/modules/registry";

/**
 * Lateral module shell is visible when any registered module is enabled
 * (production modules: Viabilidad, Tendencias, Oportunidades).
 * Escape: ?modulesShell=off hides the entire shell.
 */
export function isModulesShellVisible(): boolean {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const shell = params.get("modulesShell")?.trim().toLowerCase();
    if (shell === "off" || shell === "false" || shell === "0") return false;
    if (shell === "pilot" || shell === "1" || shell === "true") return true;
  }
  if (process.env.NEXT_PUBLIC_MODULES_SHELL_PILOT === "true") return true;
  try {
    return getVisibleModules().length > 0;
  } catch {
    return false;
  }
}

/** @deprecated use isModulesShellVisible */
export function isModulesShellPilot(): boolean {
  return isModulesShellVisible();
}
