"use client";

import { Suspense } from "react";

import { HudPanel } from "@ced/ui";

import { CAROUSEL_PANEL_HEIGHT_PX } from "@/components/dashboard/carousel/carouselLayout";
import { LeftPanel3DCarousel } from "@/components/dashboard/LeftPanel3DCarousel";
import { HudCollapsible } from "@/components/hud/HudCollapsible";
import { MetaOAuthCallbackBanner } from "@/components/hud/ConnectNetworksButton";
import { TrialExpiredBanner } from "@/components/billing/TrialExpiredBanner";
import { HudDronesPanel } from "@/components/hud/HudDronesPanel";
import {
  HudGlobalPanel,
  HudGlobalPanelFrame,
  HudSummaryPanel,
  HudSummaryPanelFrame,
  HudWavesPanel,
} from "@/components/hud/HudLivePanels";
import { HudUsageBar } from "@/components/hud/HudUsageBar";
import { CedVoiceHub } from "@/components/voice/CedVoiceHub";
import { HudFeedProvider } from "@/contexts/HudFeedContext";
import { HudPanelProvider } from "@/contexts/HudPanelContext";

/** HUD — 3 columnas desktop; móvil con paneles colapsables. */
export function HudDashboardGrid() {
  return (
    <HudFeedProvider>
      <HudPanelProvider>
        <div className="hidden grid-cols-12 gap-4 p-4 lg:grid lg:items-start">
          <div className="col-span-12">
            <Suspense fallback={null}>
              <MetaOAuthCallbackBanner />
              <TrialExpiredBanner />
            </Suspense>
          </div>
          <div className="col-span-4">
          <div
            className="w-full"
            style={{
              height: CAROUSEL_PANEL_HEIGHT_PX,
              maxHeight: CAROUSEL_PANEL_HEIGHT_PX,
            }}
          >
            <HudPanel
              title="CASTILLO"
              className="h-full max-h-full shrink-0"
              bodyClassName="flex shrink-0 flex-col px-4 py-2"
            >
              <LeftPanel3DCarousel />
            </HudPanel>
          </div>
          </div>
          <div className="col-span-4 flex flex-col items-center justify-center py-2">
            <CedVoiceHub />
          </div>
          <div className="col-span-4">
            <HudGlobalPanelFrame>
              <HudGlobalPanel />
            </HudGlobalPanelFrame>
          </div>
          <div className="col-span-3">
            <HudPanel title="DRONES" className="min-h-[200px]">
              <HudDronesPanel />
            </HudPanel>
          </div>
          <div className="col-span-6">
            <HudSummaryPanelFrame>
              <HudSummaryPanel />
            </HudSummaryPanelFrame>
          </div>
          <div className="col-span-3">
            <HudPanel title="WAVES" className="min-h-[150px]">
              <HudWavesPanel />
            </HudPanel>
          </div>
          <div className="col-span-12">
            <HudPanel title="USAGE" state="idle">
              <HudUsageBar />
            </HudPanel>
          </div>
        </div>

        <div className="flex flex-col gap-2 p-3 pb-6 lg:hidden">
          <Suspense fallback={null}>
            <MetaOAuthCallbackBanner />
          </Suspense>
          <CedVoiceHub />
          <HudCollapsible title="CASTILLO" defaultOpen>
            <LeftPanel3DCarousel />
          </HudCollapsible>
          <HudCollapsible title="GLOBAL">
            <HudGlobalPanel />
          </HudCollapsible>
          <HudCollapsible title="DRONES">
            <HudDronesPanel />
          </HudCollapsible>
          <HudCollapsible title="SUMMARY">
            <HudSummaryPanel />
          </HudCollapsible>
          <HudCollapsible title="WAVES">
            <HudWavesPanel />
          </HudCollapsible>
          <HudCollapsible title="USAGE" defaultOpen>
            <HudUsageBar />
          </HudCollapsible>
        </div>
      </HudPanelProvider>
    </HudFeedProvider>
  );
}
