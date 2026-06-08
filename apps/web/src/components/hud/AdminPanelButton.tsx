import Link from "next/link";

/** Visible solo cuando isSuperAdmin=true (decisión en layout servidor). */
export function AdminPanelButton({ visible }: { visible: boolean }) {
  if (!visible) {
    return null;
  }
  return (
    <Link
      href="/admin"
      className="flex shrink-0 items-center gap-1.5 rounded border-2 border-cyan-400 bg-cyan-400/15 px-2.5 py-1.5 font-[family-name:var(--font-orbitron)] text-[9px] font-bold tracking-wider text-cyan-200 transition hover:bg-cyan-400/30 ced-glow sm:gap-2 sm:px-4 sm:py-2 sm:text-[10px]"
    >
      <span aria-hidden>🏰</span>
      <span>ADMIN</span>
    </Link>
  );
}
