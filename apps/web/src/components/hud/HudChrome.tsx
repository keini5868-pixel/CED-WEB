"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Navigation } from "lucide-react";

import { AdminPanelButton } from "@/components/hud/AdminPanelButton";
import { BibleVerseTicker } from "@/components/hud/BibleVerseTicker";
import { ConnectNetworksButton } from "@/components/hud/ConnectNetworksButton";
import { HudNavMenu } from "@/components/hud/HudNavMenu";
import { SignOutButton } from "@/components/auth/SignOutButton";
import { useDriveMap } from "@/contexts/DriveMapContext";
import { CedWordmark } from "@/components/brand/CedWordmark";
import {
  ACCOUNT_PATH,
  DASHBOARD_PATH,
  TEAM_PATH,
} from "@/lib/auth/paths";
import {
  dispatchCedOpenModule,
  dispatchCedOpenSettings,
  isDashboardPath,
} from "@/lib/hud/chrome-events";
import { isOpportunitiesModuleEnabled } from "@/lib/pilot/opportunitiesModule";
import { isTrendsModuleEnabled } from "@/lib/pilot/trendsModule";
import { isViabilityModuleEnabled } from "@/lib/pilot/viabilityModule";
import { isVideoEditModulePilot } from "@/lib/pilot/videoEditModule";
import { MODULE_DISPLAY } from "@/lib/modules/displayNames";

type HudChromeProps = {
  email?: string | null;
  isSuperAdmin: boolean;
};

export function HudChrome({ email, isSuperAdmin }: HudChromeProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { openDriveMap } = useDriveMap();
  const onDashboard = isDashboardPath(pathname);

  function openModule(id: string) {
    if (onDashboard) {
      dispatchCedOpenModule(id);
      return;
    }
    router.push(`${DASHBOARD_PATH}?mod=${encodeURIComponent(id)}`);
  }

  function openSettings() {
    if (onDashboard) {
      dispatchCedOpenSettings();
      return;
    }
    router.push(`${DASHBOARD_PATH}?settings=1`);
  }

  const sistemaMenu = (
    <HudNavMenu
      label="Sistema"
      align="left"
      tone="navy"
      items={[
        { id: "plans", label: "Planes", href: "/dashboard/plans" },
        { id: "account", label: "Cuentas", href: ACCOUNT_PATH },
        { id: "history", label: "Historial", href: "/historial" },
        { id: "media", label: "Imágenes y PDF", href: "/historial?tab=archivos" },
        { id: "trash", label: "Papelera", href: "/historial?tab=papelera" },
        { id: "settings", label: "Configuración", onClick: openSettings },
      ]}
    />
  );

  const estrategiaMenu = (
    <HudNavMenu
      label="Estrategia"
      align="right"
      tone="navy"
      items={[
        {
          id: "viability",
          label: MODULE_DISPLAY.viability,
          hidden: !isViabilityModuleEnabled(),
          onClick: () => openModule("viability"),
        },
        {
          id: "trends",
          label: MODULE_DISPLAY.trends,
          hidden: !isTrendsModuleEnabled(),
          onClick: () => openModule("trends"),
        },
        {
          id: "opportunities",
          label: MODULE_DISPLAY.opportunities,
          hidden: !isOpportunitiesModuleEnabled(),
          onClick: () => openModule("opportunities"),
        },
        { id: "team", label: MODULE_DISPLAY.team, href: TEAM_PATH },
        {
          id: "video-edit",
          label: "Edición de video",
          hidden: !isVideoEditModulePilot(),
          onClick: () => openModule("video-edit"),
        },
      ]}
    />
  );

  return (
    <header
      className="ced-chrome-bar z-50 w-full max-w-[100vw] shrink-0 overflow-x-hidden shadow-[0_8px_24px_rgba(7,47,61,0.4)]"
    >
      <div className="mx-auto flex h-10 w-full max-w-screen items-center gap-1 px-2 sm:h-auto sm:gap-2 sm:px-4 sm:py-2.5 md:px-6">
        <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
          <Link
            href={DASHBOARD_PATH}
            className="flex shrink-0 items-center gap-1.5"
            aria-label="CED — Castillo de la Evolución Digital"
          >
            <span
              className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--ced-cyan)]/80 bg-[var(--ced-cyan)]/20 shadow-[0_0_14px_var(--ced-cyan-glow)] sm:h-8 sm:w-8"
              aria-hidden
            >
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--ced-cyan)] sm:h-3.5 sm:w-3.5" />
            </span>
            <CedWordmark size="sm" className="text-[11px] sm:text-lg sm:tracking-[0.16em]" />
          </Link>
          <div className="flex shrink-0 items-center">{sistemaMenu}</div>
          <button
            type="button"
            onClick={() => openDriveMap()}
            title="Mapa"
            aria-label="Abrir mapa"
            className="inline-flex shrink-0 rounded-lg border border-white/20 p-1 text-sky-100 hover:border-sky-200 hover:bg-white/10 hover:text-white sm:p-1.5"
          >
            <Navigation className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
          <div className="min-w-0 flex-1 px-1 sm:px-3">
            <BibleVerseTicker />
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-1 sm:gap-2">
          {onDashboard ? null : estrategiaMenu}
          <div className="hidden items-center gap-1 md:flex md:gap-2">
            <ConnectNetworksButton />
          </div>
          <AdminPanelButton visible={isSuperAdmin} />
          {email ? (
            <span className="hidden max-w-[140px] truncate text-[10px] text-sky-100/80 xl:inline">
              {email}
            </span>
          ) : null}
          <SignOutButton className="!px-2 !py-1 !text-[9px] !text-white sm:!px-2 sm:!py-1.5 sm:!text-[10px]" />
        </div>
      </div>
    </header>
  );
}
