import { HudPanel } from "@ced/ui";

import { AdminSupportInbox } from "@/components/admin/AdminSupportInbox";

export default function AdminSupportPage() {
  return (
    <div className="space-y-4">
      <HudPanel title="SOPORTE — CONVERSACIONES" className="col-span-full border-0 bg-transparent p-0 shadow-none">
        <AdminSupportInbox />
      </HudPanel>
    </div>
  );
}
