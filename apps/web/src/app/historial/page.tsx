import { Suspense } from "react";

import { HistorialHub } from "@/components/historial/HistorialHub";

export default function HistorialPage() {
  return (
    <Suspense
      fallback={
        <p className="ced-hud-text-muted px-4 py-8 text-sm">Cargando historial…</p>
      }
    >
      <HistorialHub />
    </Suspense>
  );
}
