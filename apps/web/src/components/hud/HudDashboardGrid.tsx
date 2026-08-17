"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

import { HudPanel } from "@ced/ui";

import { HudCollapsible } from "@/components/hud/HudCollapsible";
import { MetaOAuthCallbackBanner } from "@/components/hud/ConnectNetworksButton";
import { TrialExpiredBanner } from "@/components/billing/TrialExpiredBanner";
import { BillingFeedback } from "@/components/billing/BillingFeedback";
import { CierrePartnerPreviewBanner } from "@/components/preview/CierrePartnerPreviewBanner";
import {
  HudGlobalPanel,
  HudGlobalPanelFrame,
} from "@/components/hud/HudLivePanels";
import { HudUsageBar } from "@/components/hud/HudUsageBar";
import { HudFeedProvider } from "@/contexts/HudFeedContext";
import { HudPanelProvider } from "@/contexts/HudPanelContext";
import { useBreakpointLg } from "@/hooks/useBreakpointLg";
import { UsageBalanceProvider } from "@/hooks/useUsageBalance";

const CedVoiceHub = dynamic(
  () => import("@/components/voice/CedVoiceHub").then((m) => m.CedVoiceHub),
  { ssr: false },
);

/** HUD — voz, conversación y uso. Sin carrusel CASTILLO ni paneles LIFE/DRONES/WAVES. */
export function HudDashboardGrid() {
  const isLg = useBreakpointLg();
  return (
    <HudFeedProvider>
      <HudPanelProvider>
        <UsageBalanceProvider>
        <div className="hidden grid-cols-12 gap-4 p-4 pb-24 lg:grid lg:items-start">
          <div className="col-span-12">
            <Suspense fallback={null}>
              <BillingFeedback />
              <MetaOAuthCallbackBanner />
              <TrialExpiredBanner />
              <CierrePartnerPreviewBanner />
            </Suspense>
          </div>
          <div className="col-span-8 flex flex-col items-center justify-center gap-3 py-2">
            {isLg === true ? <CedVoiceHub /> : null}
          </div>
          <div className="col-span-4">
            <HudGlobalPanelFrame>
              <HudGlobalPanel />
            </HudGlobalPanelFrame>
          </div>
          <div className="col-span-12">
            <HudPanel title="USAGE" state="idle">
              <HudUsageBar />
            </HudPanel>
          </div>
        </div>

        <div className="flex flex-col gap-2 p-3 pb-24 lg:hidden">
          <Suspense fallback={null}>
            <BillingFeedback />
            <MetaOAuthCallbackBanner />
            <TrialExpiredBanner />
            <CierrePartnerPreviewBanner />
          </Suspense>
          {isLg === false ? <CedVoiceHub /> : null}
          <HudCollapsible title="CONVERSACIÓN">
            <HudGlobalPanel />
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
