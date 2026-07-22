import { Briefcase, Target, TrendingUp } from "lucide-react";

import { isOpportunitiesModulePilot } from "@/lib/pilot/opportunitiesModule";
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
    isPilotEnabled: isViabilityModulePilot,
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
    isPilotEnabled: isTrendsModulePilot,
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
    isPilotEnabled: isOpportunitiesModulePilot,
    load: () =>
      import("@/components/pilot/OpportunitiesPilotPanel").then((m) => ({
        default: m.OpportunitiesModuleContent,
      })),
  },
];

export function getPilotVisibleModules(): CedModuleRegistration[] {
  return CED_MODULE_REGISTRY.filter((m) => {
    try {
      return m.isPilotEnabled();
    } catch {
      return false;
    }
  });
}

export function getModuleById(id: string): CedModuleRegistration | undefined {
  return CED_MODULE_REGISTRY.find((m) => m.id === id);
}
