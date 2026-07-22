import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";

/** Props for every self-contained module mini-UI. */
export type ModulePanelProps = {
  onClose: () => void;
};

export type CedModuleRegistration = {
  id: string;
  name: string;
  /** Short label under icon (≤8 chars ideal) */
  short: string;
  icon: LucideIcon;
  /** Pilot gate — module hidden unless this returns true */
  isPilotEnabled: () => boolean;
  /**
   * Lazy entry point. Unmounted on close → state discarded (signed-off policy).
   * Must not read/write main CED chat or voice session state.
   */
  load: () => Promise<{ default: ComponentType<ModulePanelProps> }>;
};
