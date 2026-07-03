import type { NavPlaceOption, NavRoute } from "@/lib/api/navigation";

export type MapState = "idle" | "searching" | "ruta_lista" | "navegando";

export const MAP_UI_VISIBILITY = {
  idle: { searchBar: true, results: false, routePreview: false, navPanel: false },
  searching: { searchBar: true, results: true, routePreview: false, navPanel: false },
  ruta_lista: { searchBar: false, results: false, routePreview: true, navPanel: false },
  navegando: { searchBar: false, results: false, routePreview: false, navPanel: true },
} as const;

export function deriveMapState(input: {
  route: NavRoute | null;
  placeOptions: NavPlaceOption[];
  isSearching: boolean;
  isNavigating: boolean;
}): MapState {
  if (input.route && input.isNavigating) return "navegando";
  if (input.route) return "ruta_lista";
  if (input.isSearching || input.placeOptions.length > 0) return "searching";
  return "idle";
}
