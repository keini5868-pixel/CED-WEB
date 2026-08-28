import { Briefcase, Clapperboard, Target, TrendingUp, Workflow } from "lucide-react";

import { isAutomationModulePilot } from "@/lib/pilot/automationModule";
import { isOpportunitiesModuleEnabled } from "@/lib/pilot/opportunitiesModule";
import { isTrendsModuleEnabled } from "@/lib/pilot/trendsModule";
import { isViabilityModuleEnabled } from "@/lib/pilot/viabilityModule";
import { isVideoEditModulePilot } from "@/lib/pilot/videoEditModule";
import { MODULE_DISPLAY } from "@/lib/modules/displayNames";
import type { CedModuleRegistration } from "@/modules/types";

/**
 * Module shell registry — append here to add a module.
 * Do not wire new modules into CedVoiceControls, text_chat, or shared session.
 */
export const CED_MODULE_REGISTRY: CedModuleRegistration[] = [
  {
    id: "viability",
    name: MODULE_DISPLAY.viability,
    short: "PROD",
    icon: Target,
    stage: "production",
    isEnabled: isViabilityModuleEnabled,
    load: () =>
      import("@/components/pilot/ViabilityPilotPanel").then((m) => ({
        default: m.ViabilityModuleContent,
      })),
  },
  {
    id: "trends",
    name: MODULE_DISPLAY.trends,
    short: "TEND",
    icon: TrendingUp,
    stage: "production",
    isEnabled: isTrendsModuleEnabled,
    load: () =>
      import("@/components/pilot/TrendsPilotPanel").then((m) => ({
        default: m.TrendsModuleContent,
      })),
  },
  {
    id: "opportunities",
    name: MODULE_DISPLAY.opportunities,
    short: "OPPS",
    icon: Briefcase,
    stage: "production",
    isEnabled: isOpportunitiesModuleEnabled,
    load: () =>
      import("@/components/pilot/OpportunitiesPilotPanel").then((m) => ({
        default: m.OpportunitiesModuleContent,
      })),
  },
  {
    id: "automation",
    name: MODULE_DISPLAY.automation,
    short: "AUTO",
    icon: Workflow,
    stage: "pilot",
    isEnabled: isAutomationModulePilot,
    load: () =>
      import("@/components/pilot/AutomationPilotPanel").then((m) => ({
        default: m.AutomationModuleContent,
      })),
  },
  {
    id: "video-edit",
    name: "Edición de video",
    short: "VIDEO",
    icon: Clapperboard,
    stage: "pilot",
    isEnabled: isVideoEditModulePilot,
    load: () =>
      import("@/components/pilot/VideoEditPilotPanel").then((m) => ({
        default: m.VideoEditModuleContent,
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
