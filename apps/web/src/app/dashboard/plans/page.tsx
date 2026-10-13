import { PlansPanel } from "@/components/billing/PlansPanel";

/** En studio el body no hace scroll; esta ruta debe desplazarse sola. */
export default function DashboardPlansPage() {
  return (
    <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-y-contain [-webkit-overflow-scrolling:touch] pb-[max(6rem,env(safe-area-inset-bottom))]">
      <PlansPanel />
    </div>
  );
}
