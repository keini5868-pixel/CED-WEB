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
      items={[
        { id: "plans", label: "Planes", href: "/dashboard/plans" },
        { id: "account", label: "Cuentas", href: ACCOUNT_PATH },
        { id: "history", label: "Historial", href: "/historial" },
        { id: "settings", label: "Configuración", onClick: openSettings },
      ]}
    />
  );

  const estrategiaMenu = (
    <HudNavMenu
      label="Estrategia"
      align="right"
      items={[
        {
          id: "viability",
          label: "Viabilidad",
          hidden: !isViabilityModuleEnabled(),
          onClick: () => openModule("viability"),
        },
        {
          id: "trends",
          label: "Trends",
          hidden: !isTrendsModuleEnabled(),
          onClick: () => openModule("trends"),
        },
        {
          id: "opportunities",
          label: "Oportunidades",
          hidden: !isOpportunitiesModuleEnabled(),
          onClick: () => openModule("opportunities"),
        },
        { id: "team", label: "Mi Equipo", href: TEAM_PATH },
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
    <header className="sticky top-0 z-50 w-full max-w-[100vw] overflow-visible border-b border-cyan-500/20 bg-[var(--ced-bg)]/95 backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-screen items-center gap-1 px-2 py-2 sm:gap-2 sm:px-4 sm:py-2.5 md:px-6">
        <div className="flex shrink-0 items-center">{sistemaMenu}</div>

        <div className="flex min-w-0 flex-1 items-center justify-center gap-1.5 px-1 md:justify-start md:px-2">
          <Link
            href={DASHBOARD_PATH}
            className="shrink-0 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-widest text-cyan-300 ced-glow-text sm:text-sm"
          >
            CED
          </Link>
          <button
            type="button"
            onClick={() => openDriveMap()}
            title="Mapa"
            aria-label="Abrir mapa"
            className="inline-flex shrink-0 rounded border border-cyan-500/30 p-1.5 text-cyan-400 hover:border-cyan-400/60 hover:text-cyan-200"
          >
            <Navigation className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
          <div className="hidden min-w-0 flex-1 justify-center px-3 md:flex">
            <BibleVerseTicker />
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-1 sm:gap-2">
          {estrategiaMenu}
          <div className="hidden items-center gap-1 md:flex md:gap-2">
            <ConnectNetworksButton />
            <AdminPanelButton visible={isSuperAdmin} />
            {email ? (
              <span className="ced-hud-text-body hidden max-w-[140px] truncate text-[10px] xl:inline">
                {email}
              </span>
            ) : null}
            <SignOutButton className="!px-2 !py-1.5 !text-[9px] sm:!text-[10px]" />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 border-t border-cyan-500/10 px-2 py-1 sm:px-3 md:hidden">
        <div className="min-w-0 flex-1">
          <BibleVerseTicker />
        </div>
        <AdminPanelButton visible={isSuperAdmin} />
        <SignOutButton className="!px-2 !py-1 !text-[9px]" />
      </div>
    </header>
  );
}
