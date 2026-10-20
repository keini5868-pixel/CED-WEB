import { Suspense } from "react";

import { MailModulePanel } from "@/components/mail/MailModulePanel";

export default function DashboardCorreoPage() {
  return (
    <div className="h-full min-h-0 overflow-hidden">
      <Suspense fallback={null}>
        <MailModulePanel />
      </Suspense>
    </div>
  );
}
