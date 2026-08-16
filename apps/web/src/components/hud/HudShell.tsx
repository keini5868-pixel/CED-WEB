import { HudChrome } from "@/components/hud/HudChrome";

interface HudShellProps {
  children: React.ReactNode;
  email?: string | null;
  isSuperAdmin: boolean;
}

export function HudShell({ children, email, isSuperAdmin }: HudShellProps) {
  return (
    <div className="flex min-h-screen flex-col overflow-x-hidden bg-[var(--ced-bg)]">
      <HudChrome email={email} isSuperAdmin={isSuperAdmin} />
      <main className="ced-hud-page-bg flex-1">{children}</main>
    </div>
  );
}
