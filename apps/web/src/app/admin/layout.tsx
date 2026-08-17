import { redirect } from "next/navigation";

import { HudShell } from "@/components/hud/HudShell";
import { AdminNav } from "@/components/admin/AdminNav";
import { getSession } from "@/lib/auth/session";
import { isSupabaseConfigured } from "@/lib/env";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  if (!isSupabaseConfigured()) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p className="text-sm text-cyan-500">
          Panel admin disponible tras configurar Supabase.
        </p>
      </main>
    );
  }

  const { user, isSuperAdmin: admin } = await getSession();

  if (!user) {
    redirect("/login?next=/admin");
  }
  if (!admin) {
    redirect("/dashboard");
  }

  return (
    <HudShell email={user.email} isSuperAdmin>
      <div className="border-b border-[var(--ced-cyan)]/30 bg-[#0a0a0a] px-4 py-2.5 ced-mark-text text-sm uppercase">
        MODO ADMINISTRADOR
      </div>
      <AdminNav />
      {children}
    </HudShell>
  );
}
