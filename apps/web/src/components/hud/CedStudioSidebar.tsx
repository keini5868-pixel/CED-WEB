"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { TEAM_PATH } from "@/lib/auth/paths";
import { dispatchCedOpenModule } from "@/lib/hud/chrome-events";
import { isOpportunitiesModuleEnabled } from "@/lib/pilot/opportunitiesModule";
import { isTrendsModuleEnabled } from "@/lib/pilot/trendsModule";
import { isViabilityModuleEnabled } from "@/lib/pilot/viabilityModule";
import { isVideoEditModulePilot } from "@/lib/pilot/videoEditModule";
import { MODULE_DISPLAY } from "@/lib/modules/displayNames";

type SidebarLink = {
  id: string;
  label: string;
  href?: string;
  onClick?: () => void;
  hidden?: boolean;
};

const linkClass =
  "ced-mark-text ced-gold-outline rounded-lg px-2 py-2 text-left text-[14px] uppercase transition hover:bg-[var(--ced-cyan)]/10";

export function CedStudioSidebar({
  listen,
  usage,
  extras,
}: {
  listen: ReactNode;
  usage?: ReactNode;
  extras?: ReactNode;
}) {
  const links: SidebarLink[] = [
    {
      id: "viability",
      label: MODULE_DISPLAY.viability,
      hidden: !isViabilityModuleEnabled(),
      onClick: () => dispatchCedOpenModule("viability"),
    },
    {
      id: "trends",
      label: MODULE_DISPLAY.trends,
      hidden: !isTrendsModuleEnabled(),
      onClick: () => dispatchCedOpenModule("trends"),
    },
    {
      id: "opportunities",
      label: MODULE_DISPLAY.opportunities,
      hidden: !isOpportunitiesModuleEnabled(),
      onClick: () => dispatchCedOpenModule("opportunities"),
    },
    { id: "team", label: MODULE_DISPLAY.team, href: TEAM_PATH },
    {
      id: "video-edit",
      label: "Edición de video",
      hidden: !isVideoEditModulePilot(),
      onClick: () => dispatchCedOpenModule("video-edit"),
    },
  ];

  return (
    <aside className="flex w-full shrink-0 flex-col overflow-hidden border-t border-[var(--studio-border)] bg-[var(--studio-sidebar)] px-5 py-5 lg:h-full lg:w-[min(15.5rem,28%)] lg:border-l lg:border-t-0">
      <nav aria-label="Módulos CED" className="flex min-h-0 flex-col gap-0.5 overflow-y-auto">
        {links
          .filter((item) => !item.hidden)
          .map((item) =>
            item.href ? (
              <Link key={item.id} href={item.href} className={linkClass}>
                {item.label}
              </Link>
            ) : (
              <button
                key={item.id}
                type="button"
                onClick={item.onClick}
                className={linkClass}
              >
                {item.label}
              </button>
            ),
          )}
      </nav>

      {extras ? <div className="mt-3 flex flex-col gap-1">{extras}</div> : null}

      <div className="mt-auto flex shrink-0 flex-col items-center gap-3 pt-6">
        {listen}
        {usage ? <div className="w-full pt-1">{usage}</div> : null}
      </div>
    </aside>
  );
}
