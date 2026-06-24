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
    <div className="flex min-h-screen flex-col bg-[var(--ced-bg)]">
      <header className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-cyan-500/20 bg-[var(--ced-bg)]/95 px-3 py-2 backdrop-blur-sm sm:gap-3 sm:px-4 sm:py-3 md:px-6">
        <div className="flex shrink-0 items-center gap-4">
          <Link
            href="/dashboard"
            className="font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-widest text-cyan-300 ced-glow-text"
          >
            CED
          </Link>
          <span className="ced-hud-text-muted hidden text-xs md:inline">
            SYS: ONLINE
          </span>
        </div>
        <div className="hidden min-w-0 flex-1 justify-center px-2 md:flex">
          <BibleVerseTicker />
        </div>
        <div className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-2 sm:gap-3 md:ml-0">
          <DriveModeLink compact />
          <Link
            href="/historial"
            className="text-[10px] font-semibold uppercase tracking-wider text-cyan-600 hover:text-cyan-300"
          >
            Historial
          </Link>
          <AdminPanelButton visible={isSuperAdmin} />
          <ConnectNetworksButton />
          {email ? (
            <span className="ced-hud-text-body max-w-[180px] truncate text-xs">
              {email}
            </span>
          ) : null}
          <SignOutButton />
        </div>
      </header>
      <main className="ced-hud-page-bg flex-1">{children}</main>
    </div>
  );
}
