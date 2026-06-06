import { HudPanel } from "@ced/ui";

import { AdminMyUsageReset } from "@/components/admin/AdminMyUsageReset";
import { AdminUsersPanel } from "@/components/admin/AdminUsersPanel";

export default function AdminPage() {
  return (
    <div className="space-y-4 p-4">
      <HudPanel title="USUARIOS REGISTRADOS" className="col-span-full">
        <AdminUsersPanel />
      </HudPanel>

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
    </div>
  );
}
