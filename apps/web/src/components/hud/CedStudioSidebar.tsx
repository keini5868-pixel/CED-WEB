"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { TEAM_PATH } from "@/lib/auth/paths";
import { dispatchCedOpenModule } from "@/lib/hud/chrome-events";
import { isOpportunitiesModuleEnabled } from "@/lib/pilot/opportunitiesModule";
import { isTrendsModuleEnabled } from "@/lib/pilot/trendsModule";
import { isViabilityModuleEnabled } from "@/lib/pilot/viabilityModule";
import { isVideoEditModulePilot } from "@/lib/pilot/videoEditModule";

type SidebarLink = {
  id: string;
  label: string;
  href?: string;
  onClick?: () => void;
  hidden?: boolean;
};

const linkClass =
  "rounded-lg px-2 py-2 text-left text-[15px] font-semibold tracking-wide text-[#0c3d73] transition hover:bg-sky-100 hover:text-[#08284c]";

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
      label: "Viabilidad",
      hidden: !isViabilityModuleEnabled(),
      onClick: () => dispatchCedOpenModule("viability"),
    },
    {
      id: "trends",
      label: "Trends",
      hidden: !isTrendsModuleEnabled(),
      onClick: () => dispatchCedOpenModule("trends"),
    },
    {
      id: "opportunities",
      label: "Oportunidades",
      hidden: !isOpportunitiesModuleEnabled(),
      onClick: () => dispatchCedOpenModule("opportunities"),
    },
    { id: "team", label: "Mi Equipo", href: TEAM_PATH },
    {
      id: "video-edit",
      label: "Edición de video",
      hidden: !isVideoEditModulePilot(),
      onClick: () => dispatchCedOpenModule("video-edit"),
    },
  ];

  return (
    <aside className="flex w-full flex-col border-t border-sky-100 bg-[#f4f9fd] px-5 py-5 lg:w-[min(15.5rem,28%)] lg:shrink-0 lg:border-l lg:border-t-0">
      <nav aria-label="Módulos CED" className="flex flex-col gap-0.5">
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

      <div className="mt-auto flex flex-col items-center gap-3 pt-6">
        {listen}
        {usage ? <div className="w-full pt-1">{usage}</div> : null}
      </div>
    </aside>
  );
}
