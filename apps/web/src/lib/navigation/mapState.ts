import type { NavPlaceOption, NavRoute } from "@/lib/api/navigation";

export type MapState = "idle" | "searching" | "navigating";

export const MAP_UI_VISIBILITY = {
  idle: { searchBar: true, results: false, navPanel: false },
  searching: { searchBar: true, results: true, navPanel: false },
  navigating: { searchBar: false, results: false, navPanel: true },
} as const;

export function deriveMapState(input: {
  route: NavRoute | null;
  placeOptions: NavPlaceOption[];
  isSearching: boolean;
}): MapState {
  if (input.route) return "navigating";
  if (input.isSearching || input.placeOptions.length > 0) return "searching";
  return "idle";
}
