import { HudShell } from "@/components/hud/HudShell";
import { getSession } from "@/lib/auth/session";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isSuperAdmin: admin } = await getSession();

  return (
    <HudShell email={user?.email ?? null} isSuperAdmin={admin}>
      {children}
    </HudShell>
  );
}
