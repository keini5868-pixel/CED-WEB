import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";

/** Props for every self-contained module mini-UI. */
export type ModulePanelProps = {
  onClose: () => void;
};

export type CedModuleStage = "pilot" | "production";

export type CedModuleRegistration = {
  id: string;
  name: string;
  /** Short label under icon (≤8 chars ideal) */
  short: string;
  icon: LucideIcon;
  /** pilot = query/env flag; production = on for logged-in users (kill-switch may hide) */
  stage: CedModuleStage;
  /** Module visible in the rail when this returns true */
  isEnabled: () => boolean;
  /**
   * Lazy entry point. Unmounted on close → state discarded (signed-off policy).
   * Must not read/write main CED chat or voice session state.
   */
  load: () => Promise<{ default: ComponentType<ModulePanelProps> }>;
};
