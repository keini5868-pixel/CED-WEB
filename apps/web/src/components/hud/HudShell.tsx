import { HudChrome } from "@/components/hud/HudChrome";

interface HudShellProps {
  children: React.ReactNode;
  email?: string | null;
  isSuperAdmin: boolean;
  studio?: boolean;
}

export function HudShell({ children, email, isSuperAdmin, studio = false }: HudShellProps) {
  return (
    <div
      className={[
        "flex flex-col overflow-x-hidden",
        studio ? "ced-studio-shell" : "min-h-screen bg-[var(--ced-bg)]",
      ].join(" ")}
    >
      <HudChrome email={email} isSuperAdmin={isSuperAdmin} />
      <main
        className={[
          "flex min-h-0 flex-1 flex-col",
          studio ? "overflow-y-auto bg-white" : "ced-hud-page-bg",
        ].join(" ")}
      >
        {children}
      </main>
    </div>
  );
}
