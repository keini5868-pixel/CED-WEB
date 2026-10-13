"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { dismissDashboardOverlays } from "@/lib/hud/chrome-events";

/** Visible solo cuando isSuperAdmin=true (decisión en layout servidor). */
export function AdminPanelButton({ visible }: { visible: boolean }) {
  const router = useRouter();

  if (!visible) {
    return null;
  }

  function openAdmin() {
    dismissDashboardOverlays();
    router.push("/admin");
  }

  return (
    <Link
      href="/admin"
      data-ced-hotspot="admin"
      onClick={(ev) => {
        ev.preventDefault();
        openAdmin();
      }}
      className="relative z-[501] flex shrink-0 items-center gap-1 rounded border-2 border-cyan-400 bg-cyan-400/15 px-1.5 py-0.5 font-[family-name:var(--font-orbitron)] text-[8px] font-bold tracking-wider text-cyan-200 transition hover:bg-cyan-400/30 ced-glow sm:gap-2 sm:px-4 sm:py-2 sm:text-[10px]"
    >
      <span aria-hidden>🏰</span>
      <span>ADMIN</span>
    </Link>
  );
}
