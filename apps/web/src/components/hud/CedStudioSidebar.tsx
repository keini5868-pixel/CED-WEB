"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { MOBILE_COMPOSER_DOCK_ID } from "@/components/chat/MobileComposerDock";
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
  shortLabel?: string;
  href?: string;
  onClick?: () => void;
  hidden?: boolean;
};

const linkClass =
  "ced-mark-text rounded-lg px-1 py-1.5 text-center text-[8px] uppercase leading-tight transition hover:bg-[var(--ced-cyan)]/10 sm:text-[9px] lg:px-2 lg:py-2 lg:text-left lg:text-[14px] lg:leading-normal";

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
      shortLabel: "Producto",
      hidden: !isViabilityModuleEnabled(),
      onClick: () => dispatchCedOpenModule("viability"),
    },
    {
      id: "trends",
      label: MODULE_DISPLAY.trends,
      shortLabel: "Tendencia",
      hidden: !isTrendsModuleEnabled(),
      onClick: () => dispatchCedOpenModule("trends"),
    },
    {
      id: "opportunities",
      label: MODULE_DISPLAY.opportunities,
      shortLabel: "Oport.",
      hidden: !isOpportunitiesModuleEnabled(),
      onClick: () => dispatchCedOpenModule("opportunities"),
    },
    { id: "team", label: MODULE_DISPLAY.team, shortLabel: "Estructura", href: TEAM_PATH },
    {
      id: "video-edit",
      label: "Edición de video",
      shortLabel: "Video",
      hidden: !isVideoEditModulePilot(),
      onClick: () => dispatchCedOpenModule("video-edit"),
    },
  ];

  return (
    <aside className="flex h-full w-[6.5rem] max-w-[32vw] shrink-0 flex-col overflow-hidden border-l border-[var(--studio-border)] bg-[var(--studio-sidebar)] px-1.5 py-2 sm:w-[8rem] sm:max-w-none sm:px-2 lg:w-[min(15.5rem,28%)] lg:px-5 lg:py-5">
      <nav aria-label="Módulos CED" className="flex max-h-[34%] min-h-0 shrink-0 flex-col gap-0.5 overflow-y-auto overflow-x-hidden lg:max-h-[42%]">
        {links
          .filter((item) => !item.hidden)
          .map((item) => {
            const full = item.label;
            const short = item.shortLabel || item.label;
            const node = (
              <>
                <span className="lg:hidden">{short}</span>
                <span className="hidden lg:inline">{full}</span>
              </>
            );
            return item.href ? (
              <Link key={item.id} href={item.href} className={linkClass} title={full}>
                {node}
              </Link>
            ) : (
              <button
                key={item.id}
                type="button"
                onClick={item.onClick}
                className={linkClass}
                title={full}
              >
                {node}
              </button>
            );
          })}
      </nav>

      {extras ? <div className="mt-2 flex shrink-0 flex-col gap-0.5 overflow-x-hidden lg:mt-3">{extras}</div> : null}

      <div className="mt-auto flex min-h-0 w-full flex-1 flex-col items-center justify-end gap-2 overflow-x-hidden overflow-y-auto pt-2 lg:justify-start lg:gap-3 lg:pt-6">
        {listen}
        {usage ? <div className="w-full pt-1">{usage}</div> : null}
        <div
          id={MOBILE_COMPOSER_DOCK_ID}
          className="flex w-full shrink-0 flex-col items-center gap-1.5 pb-[max(0.25rem,env(safe-area-inset-bottom))] pt-1 lg:hidden"
        />
      </div>
    </aside>
  );
}
