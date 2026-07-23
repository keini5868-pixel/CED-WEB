import { Briefcase, Target, TrendingUp } from "lucide-react";

import { isOpportunitiesModuleEnabled } from "@/lib/pilot/opportunitiesModule";
import { isTrendsModulePilot } from "@/lib/pilot/trendsModule";
import { isViabilityModulePilot } from "@/lib/pilot/viabilityModule";
import type { CedModuleRegistration } from "@/modules/types";

/**
 * Module shell registry — append here to add a module.
 * Do not wire new modules into CedVoiceControls, text_chat, or shared session.
 */
export const CED_MODULE_REGISTRY: CedModuleRegistration[] = [
  {
    id: "viability",
    name: "Viabilidad",
    short: "VIABLE",
    icon: Target,
    stage: "pilot",
    isEnabled: isViabilityModulePilot,
    load: () =>
      import("@/components/pilot/ViabilityPilotPanel").then((m) => ({
        default: m.ViabilityModuleContent,
      })),
  },
  {
    id: "trends",
    name: "Tendencias",
    short: "TRENDS",
    icon: TrendingUp,
    stage: "pilot",
    isEnabled: isTrendsModulePilot,
    load: () =>
      import("@/components/pilot/TrendsPilotPanel").then((m) => ({
        default: m.TrendsModuleContent,
      })),
  },
  {
    id: "opportunities",
    name: "Oportunidades",
    short: "OPPS",
    icon: Briefcase,
    stage: "production",
    isEnabled: isOpportunitiesModuleEnabled,
    load: () =>
      import("@/components/pilot/OpportunitiesPilotPanel").then((m) => ({
        default: m.OpportunitiesModuleContent,
      })),
  },
];

/** Modules visible in the lateral rail (pilot flags + production kill-switches). */
export function getVisibleModules(): CedModuleRegistration[] {
  return CED_MODULE_REGISTRY.filter((m) => {
    try {
      return m.isEnabled();
    } catch {
      return false;
    }
  });
}

/** @deprecated use getVisibleModules */
export function getPilotVisibleModules(): CedModuleRegistration[] {
  return getVisibleModules();
}

export function getModuleById(id: string): CedModuleRegistration | undefined {
  return CED_MODULE_REGISTRY.find((m) => m.id === id);
}
