import type { OrbState, VoicePaletteId } from "@ced/types";

export function paletteColors(palette: VoicePaletteId) {
  const map = {
    cyan: { primary: "#00e5ff", secondary: "#7c4dff", error: "#ff5252" },
    gold: { primary: "#ffd54f", secondary: "#ff8f00", error: "#ff5252" },
    matrix: { primary: "#69f0ae", secondary: "#00c853", error: "#ff5252" },
    iron: { primary: "#ff5252", secondary: "#d50000", error: "#ff1744" },
  } as const;
  return map[palette];
}

export function stateSpeed(state: OrbState): number {
  switch (state) {
    case "idle":
      return 0.4;
    case "listening":
      return 0.9;
    case "processing":
      return 2.2;
    case "speaking":
      return 1.4;
    case "error":
      return 1.8;
    case "paused":
      return 0.15;
    default:
      return 0.4;
  }
}
