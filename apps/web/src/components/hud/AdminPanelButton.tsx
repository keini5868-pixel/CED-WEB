import Link from "next/link";

/** Visible solo cuando isSuperAdmin=true (decisión en layout servidor). */
export function AdminPanelButton({ visible }: { visible: boolean }) {
  if (!visible) {
    return null;
  }
  return (
    <Link
      href="/admin"
      className="flex items-center gap-2 rounded border-2 border-cyan-400 bg-cyan-400/15 px-4 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-200 transition hover:bg-cyan-400/30 ced-glow"
    >
      <span aria-hidden>🏰</span>
      <span>PANEL ADMIN</span>
    </Link>
  );
}
