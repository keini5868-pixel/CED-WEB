import Link from "next/link";

import { AdminPanelButton } from "@/components/hud/AdminPanelButton";
import { BibleVerseTicker } from "@/components/hud/BibleVerseTicker";
import { ConnectNetworksButton } from "@/components/hud/ConnectNetworksButton";
import { SignOutButton } from "@/components/auth/SignOutButton";
import { DriveModeLink } from "@/components/navigation/DriveModeLink";

interface HudShellProps {
  children: React.ReactNode;
  email?: string | null;
  isSuperAdmin: boolean;
}

export function HudShell({ children, email, isSuperAdmin }: HudShellProps) {
  return (
    <div className="flex min-h-screen flex-col overflow-x-hidden bg-[var(--ced-bg)]">
      <header className="sticky top-0 z-20 w-full max-w-[100vw] overflow-x-hidden border-b border-cyan-500/20 bg-[var(--ced-bg)]/95 backdrop-blur-sm">
        <div className="mx-auto flex w-full max-w-screen flex-col items-center gap-2 px-3 py-2 sm:px-4 sm:py-3 md:flex-row md:items-center md:gap-3 md:px-6">
          <div className="order-1 flex w-full shrink-0 items-center justify-center md:w-auto md:justify-start">
            <Link
              href="/dashboard"
              className="font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-widest text-cyan-300 ced-glow-text"
            >
              CED
            </Link>
            <span className="ced-hud-text-muted ml-4 hidden text-xs md:inline">
              SYS: ONLINE
            </span>
          </div>

          <nav
            className={[
              "order-2 flex w-full min-w-0 max-w-full flex-wrap items-center justify-center gap-1.5 sm:gap-2",
              "md:order-3 md:ml-auto md:w-auto md:justify-end",
              "[&_button]:!px-2.5 [&_button]:!py-1.5 [&_button]:!text-[9px] [&_button]:!tracking-wider",
              "sm:[&_button]:!px-3 sm:[&_button]:!text-[10px]",
              "md:[&_button]:!px-6 md:[&_button]:!py-3 md:[&_button]:!text-xs",
            ].join(" ")}
            aria-label="Navegación principal"
          >
            <DriveModeLink compact />
            <Link
              href="/dashboard/plans"
              className="rounded px-2 py-1.5 text-[9px] font-semibold uppercase tracking-wider text-cyan-600 hover:bg-cyan-400/5 hover:text-cyan-300 sm:px-2.5 sm:text-[10px]"
            >
              Planes
            </Link>
            <Link
              href="/historial"
              className="rounded px-2 py-1.5 text-[9px] font-semibold uppercase tracking-wider text-cyan-600 hover:bg-cyan-400/5 hover:text-cyan-300 sm:px-2.5 sm:text-[10px]"
            >
              Historial
            </Link>
            <AdminPanelButton visible={isSuperAdmin} />
            <ConnectNetworksButton />
            {email ? (
              <span className="ced-hud-text-body hidden max-w-[180px] truncate text-xs lg:inline">
                {email}
              </span>
            ) : null}
            <SignOutButton />
          </nav>

          <div className="order-3 flex w-full min-w-0 justify-center border-t border-cyan-500/10 px-2 pt-1.5 md:order-2 md:w-auto md:flex-1 md:border-t-0 md:pt-0">
            <BibleVerseTicker />
          </div>
        </div>
      </header>
      <main className="ced-hud-page-bg flex-1">{children}</main>
    </div>
  );
}
