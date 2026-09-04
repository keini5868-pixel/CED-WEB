import { HudDashboardGrid } from "@/components/hud/HudDashboardGrid";
import { HudShell } from "@/components/hud/HudShell";
import { getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

/** Vista previa — ROBOT solo si el email está en SUPER_ADMIN_EMAILS. */
export default async function HudPreviewPage() {
  const { user, isSuperAdmin, isPresenterOwner } = await getSession();

  return (
    <HudShell
      email={user?.email ?? null}
      isSuperAdmin={isSuperAdmin}
      isPresenterOwner={isPresenterOwner}
      studio
    >
      <HudDashboardGrid />
    </HudShell>
  );
}
