import { SentinelModulePanel } from "@/components/sentinel/SentinelModulePanel";

export default function DashboardSentinelPage() {
  return (
    <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-y-contain [-webkit-overflow-scrolling:touch] pb-[max(6rem,env(safe-area-inset-bottom))]">
      <SentinelModulePanel />
    </div>
  );
}
