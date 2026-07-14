import { describe, expect, it } from "vitest";

import { deriveMapState, MAP_UI_VISIBILITY } from "./mapState";
import {
  CATEGORY_OVERVIEW_MAX_ZOOM,
  DESTINATION_VIEW_TILT,
  DESTINATION_VIEW_ZOOM,
  NAV_FOLLOW_TILT,
  NAV_FOLLOW_ZOOM,
  navigationFollowZoom,
} from "./geo";

describe("deriveMapState camera modes", () => {
  it("shows destino_vista for a specific destination pin", () => {
    expect(
      deriveMapState({
        route: null,
        placeOptions: [],
        destinationPin: { lat: 48.85, lng: 2.29, label: "Torre Eiffel" },
        isSearching: false,
        isNavigating: false,
      }),
    ).toBe("destino_vista");
    expect(MAP_UI_VISIBILITY.destino_vista.results).toBe(false);
  });

  it("shows searching when there are multiple place options", () => {
    expect(
      deriveMapState({
        route: null,
        placeOptions: [
          { name: "A", lat: 1, lng: 2, address: "", distance_text: "1 km" },
          { name: "B", lat: 1.1, lng: 2.1, address: "", distance_text: "2 km" },
        ] as never,
        destinationPin: null,
        isSearching: false,
        isNavigating: false,
      }),
    ).toBe("searching");
  });

  it("prefer navigating over destination pin", () => {
    expect(
      deriveMapState({
        route: { path: [], destination: { lat: 1, lng: 2, label: "X" } } as never,
        placeOptions: [],
        destinationPin: { lat: 1, lng: 2, label: "X" },
        isSearching: false,
        isNavigating: true,
      }),
    ).toBe("navegando");
  });
});

describe("navigation camera constants", () => {
  it("keeps follow zoom close like Waze/Google", () => {
    expect(NAV_FOLLOW_ZOOM).toBeGreaterThanOrEqual(19);
    expect(NAV_FOLLOW_TILT).toBeGreaterThanOrEqual(60);
    expect(navigationFollowZoom(0)).toBeGreaterThanOrEqual(19);
    expect(DESTINATION_VIEW_ZOOM).toBeGreaterThanOrEqual(17);
    expect(DESTINATION_VIEW_TILT).toBeGreaterThanOrEqual(45);
    expect(CATEGORY_OVERVIEW_MAX_ZOOM).toBeLessThan(16);
  });
});
