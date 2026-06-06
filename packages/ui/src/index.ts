/** Tokens y utilidades UI compartidas */
export const CED_COLORS = {
  bg: "#0a0a0a",
  bgPanel: "#00060f",
  cyan: "#00e5ff",
  cyanDim: "#0097a7",
} as const;

export const CED_FONTS = {
  title: "var(--font-orbitron)",
  body: "var(--font-inter)",
} as const;

export { CedButton } from "./components/CedButton";
export { CedInput } from "./components/CedInput";
export { CedCard } from "./components/CedCard";
export { CedModal } from "./components/CedModal";
export { HudPanel } from "./components/HudPanel";
