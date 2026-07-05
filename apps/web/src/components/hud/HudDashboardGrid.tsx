"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

import { HudPanel } from "@ced/ui";

import { CAROUSEL_PANEL_HEIGHT_PX } from "@/components/dashboard/carousel/carouselLayout";
import { LeftPanel3DCarousel } from "@/components/dashboard/LeftPanel3DCarousel";
import { HudCollapsible } from "@/components/hud/HudCollapsible";
import { MetaOAuthCallbackBanner } from "@/components/hud/ConnectNetworksButton";
import { GoogleOAuthCallbackBanner } from "@/components/voice/ConnectGoogleServices";
import { TrialExpiredBanner } from "@/components/billing/TrialExpiredBanner";
import { BillingFeedback } from "@/components/billing/BillingFeedback";
import { HudDronesPanel } from "@/components/hud/HudDronesPanel";
import {
  HudGlobalPanel,
  HudGlobalPanelFrame,
  HudSummaryPanel,
  HudSummaryPanelFrame,
  HudWavesPanel,
} from "@/components/hud/HudLivePanels";
import { HudUsageBar } from "@/components/hud/HudUsageBar";
import { DriveModeLink } from "@/components/navigation/DriveModeLink";
import { HudFeedProvider } from "@/contexts/HudFeedContext";
import { HudPanelProvider } from "@/contexts/HudPanelContext";
import { useBreakpointLg } from "@/hooks/useBreakpointLg";
import { UsageBalanceProvider } from "@/hooks/useUsageBalance";

const CedVoiceHub = dynamic(
  () => import("@/components/voice/CedVoiceHub").then((m) => m.CedVoiceHub),
  { ssr: false },
);

/** HUD — 3 columnas desktop; móvil con paneles colapsables. */
export function HudDashboardGrid() {
  const isLg = useBreakpointLg();
  return (
    <HudFeedProvider>
      <HudPanelProvider>
        <UsageBalanceProvider>
        <div className="hidden grid-cols-12 gap-4 p-4 lg:grid lg:items-start">
          <div className="col-span-12">
            <Suspense fallback={null}>
              <BillingFeedback />
              <MetaOAuthCallbackBanner />
              <GoogleOAuthCallbackBanner />
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
          <div className="col-span-4 flex flex-col items-center justify-center gap-3 py-2">
            <DriveModeLink />
            {isLg === true ? <CedVoiceHub /> : null}
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

        <div className="flex flex-col gap-2 p-3 pb-[max(1.5rem,env(safe-area-inset-bottom))] lg:hidden">
          <Suspense fallback={null}>
            <BillingFeedback />
            <MetaOAuthCallbackBanner />
            <GoogleOAuthCallbackBanner />
            <TrialExpiredBanner />
          </Suspense>
          <DriveModeLink />
          {isLg === false ? <CedVoiceHub /> : null}
          <HudCollapsible title="CASTILLO" defaultOpen>
            <LeftPanel3DCarousel />
          </HudCollapsible>
          <HudCollapsible title="CONVERSACIÓN">
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
        </UsageBalanceProvider>
      </HudPanelProvider>
    </HudFeedProvider>
  );
}
