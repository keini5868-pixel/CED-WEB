"use client";

import { useRouter } from "next/navigation";

import { HudPanel } from "@ced/ui";

import { AdminMyUsageReset } from "@/components/admin/AdminMyUsageReset";
import { AdminUsersPanel } from "@/components/admin/AdminUsersPanel";

export default function AdminPage() {
  const router = useRouter();

  return (
    <div className="space-y-6 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => router.push("/admin/sentinel")}
          className="flex w-full items-center justify-between gap-3 rounded border-2 border-cyan-400 bg-cyan-400/15 px-4 py-3 text-left font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-[0.16em] text-cyan-100 shadow-[0_0_16px_var(--ced-cyan-glow)] transition hover:bg-cyan-400/25"
        >
          <span>CENTINELA OPS</span>
          <span className="text-[10px] text-cyan-200/80">GUARDIA</span>
        </button>
        <button
          type="button"
          onClick={() => router.push("/admin/sentinel-privacy")}
          className="flex w-full items-center justify-between gap-3 rounded border-2 border-violet-400/70 bg-violet-500/15 px-4 py-3 text-left font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-[0.16em] text-violet-100 shadow-[0_0_16px_rgba(120,80,255,0.35)] transition hover:bg-violet-500/25"
        >
          <span>SENTINEL PRIVACY</span>
          <span className="text-[10px] text-violet-200/80">COBROS</span>
        </button>
      </div>
      <HudPanel title="USUARIOS REGISTRADOS" className="col-span-full">
        <AdminUsersPanel />
      </HudPanel>

      <section aria-label="Herramientas admin" className="space-y-4 border-t border-cyan-500/15 pt-6">
        <p className="ced-hud-text-muted px-1 text-[10px] uppercase tracking-[0.2em]">
          Cupos y configuración
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <HudPanel title="MI CUPO DE VOZ" className="md:col-span-2">
          <AdminMyUsageReset />
        </HudPanel>
        <HudPanel title="FOUNDING">
          <p className="ced-hud-text-body">Cupos 1–50 — panel dedicado próximamente.</p>
        </HudPanel>
        <HudPanel title="AUDIT">
          <p className="ced-hud-text-body">
            Acciones en <code className="text-cyan-500">admin_audit_logs</code> al crear
            usuarios manualmente.
          </p>
        </HudPanel>
        <HudPanel title="STRIPE" className="md:col-span-2">
          <p className="ced-hud-text-body">
            Usuarios manuales no pasan por Stripe. Los de checkout normal siguen en
            webhooks.
          </p>
        </HudPanel>
        </div>
      </section>
    </div>
  );
}
