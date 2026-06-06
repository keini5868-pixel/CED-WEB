import { HudDashboardGrid } from "@/components/hud/HudDashboardGrid";
import { HudShell } from "@/components/hud/HudShell";

/** Vista previa de contraste — solo desarrollo. */
export default function HudPreviewPage() {
  return (
    <HudShell email="keini5868@gmail.com" isSuperAdmin>
      <HudDashboardGrid />
    </HudShell>
  );
}
