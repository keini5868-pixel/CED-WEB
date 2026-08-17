"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

import { MetaOAuthCallbackBanner } from "@/components/hud/ConnectNetworksButton";
import { TrialExpiredBanner } from "@/components/billing/TrialExpiredBanner";
import { BillingFeedback } from "@/components/billing/BillingFeedback";
import { CierrePartnerPreviewBanner } from "@/components/preview/CierrePartnerPreviewBanner";
import { HudFeedProvider } from "@/contexts/HudFeedContext";
import { HudPanelProvider } from "@/contexts/HudPanelContext";
import { UsageBalanceProvider } from "@/hooks/useUsageBalance";

const CedVoiceHub = dynamic(
  () => import("@/components/voice/CedVoiceHub").then((m) => m.CedVoiceHub),
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[calc(100dvh-5.5rem)] flex-1 bg-white">
        <div className="flex flex-1 items-center justify-center text-sm text-sky-800">
          Cargando asistente CED…
        </div>
        <aside className="hidden w-[15.5rem] border-l border-sky-100 bg-[#f4f9fd] lg:block" />
      </div>
    ),
  },
);

/** Dashboard studio — chat blanco + menú y voz compacta. */
export function HudDashboardGrid() {
  return (
    <HudFeedProvider>
      <HudPanelProvider>
        <UsageBalanceProvider>
        <div className="flex min-h-[calc(100dvh-5.5rem)] flex-1 flex-col">
          <div className="shrink-0 px-3 pt-3 lg:px-4">
            <Suspense fallback={null}>
              <BillingFeedback />
              <MetaOAuthCallbackBanner />
              <TrialExpiredBanner />
              <CierrePartnerPreviewBanner />
            </Suspense>
          </div>
          <CedVoiceHub />
        </div>
        </UsageBalanceProvider>
      </HudPanelProvider>
    </HudFeedProvider>
  );
}
