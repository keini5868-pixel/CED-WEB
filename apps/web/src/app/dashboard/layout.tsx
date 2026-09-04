import { HudShell } from "@/components/hud/HudShell";
import { getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isSuperAdmin: admin, isPresenterOwner } = await getSession();

  return (
    <HudShell
      email={user?.email ?? null}
      isSuperAdmin={admin}
      isPresenterOwner={isPresenterOwner}
      studio
    >
      {children}
    </HudShell>
  );
}
