import Link from "next/link";

import { AdminPanelButton } from "@/components/hud/AdminPanelButton";
import { ConnectNetworksButton } from "@/components/hud/ConnectNetworksButton";
import { SignOutButton } from "@/components/auth/SignOutButton";
import { DRIVE_PATH } from "@/lib/auth/paths";

interface HudShellProps {
  children: React.ReactNode;
  email?: string | null;
  isSuperAdmin: boolean;
}

export function HudShell({ children, email, isSuperAdmin }: HudShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--ced-bg)]">
      <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/20 bg-[var(--ced-bg)]/95 px-3 py-2 backdrop-blur-sm sm:gap-3 sm:px-4 sm:py-3 md:px-6">
        <div className="flex items-center gap-4">
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
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href={DRIVE_PATH}
            className="hidden rounded border border-cyan-700/60 px-2 py-1 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-400 hover:border-cyan-500 sm:inline"
          >
            CONDUCIR
          </Link>
          <ConnectNetworksButton />
          <AdminPanelButton visible={isSuperAdmin} />
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
