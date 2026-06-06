import { redirect } from "next/navigation";

import { HudShell } from "@/components/hud/HudShell";
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
      <div className="border-b border-cyan-500/30 bg-[#0a0a0a] px-4 py-2.5 font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-widest text-[#00e5ff]">
        MODO ADMINISTRADOR
      </div>
      {children}
    </HudShell>
  );
}
