import { HudChrome } from "@/components/hud/HudChrome";
import { CedOwnerUiProvider } from "@/contexts/CedOwnerUiContext";
import { CedPresenterSessionProvider } from "@/contexts/CedPresenterSession";

interface HudShellProps {
  children: React.ReactNode;
  email?: string | null;
  isSuperAdmin: boolean;
  /** Botón ROBOT + holograma. False por defecto: un cliente nunca lo hereda. */
  isPresenterOwner?: boolean;
  studio?: boolean;
}

export function HudShell({
  children,
  email,
  isSuperAdmin,
  isPresenterOwner = false,
  studio = false,
}: HudShellProps) {
  return (
    <CedOwnerUiProvider isOwner={isPresenterOwner}>
    <CedPresenterSessionProvider>
    <div
      className={[
        "flex max-w-[100vw] flex-col overflow-x-hidden",
        studio ? "ced-studio-shell" : "min-h-screen bg-[var(--ced-bg)]",
      ].join(" ")}
      data-ced-presenter-owner={isPresenterOwner ? "1" : "0"}
    >
      <HudChrome email={email} isSuperAdmin={isSuperAdmin} />
      <main
        className={[
          "flex min-h-0 flex-1 flex-col",
          studio
            ? "overflow-hidden bg-[var(--studio-shell-bg)]"
            : "ced-hud-page-bg",
        ].join(" ")}
      >
        {children}
      </main>
    </div>
    </CedPresenterSessionProvider>
    </CedOwnerUiProvider>
  );
}
