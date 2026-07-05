import { CED_MAP_ID } from "@/lib/maps/mapConfig";

export { CED_MAP_ID };

type MarkerLibrary = google.maps.MarkerLibrary;

let markerLibraryPromise: Promise<MarkerLibrary> | null = null;

export function loadMarkerLibrary(): Promise<MarkerLibrary> {
  if (!markerLibraryPromise) {
    markerLibraryPromise = google.maps.importLibrary("marker") as Promise<MarkerLibrary>;
  }
  return markerLibraryPromise;
}

export function createUserLocationContent(
  heading: number | null,
  navigating: boolean,
  mapRotates: boolean,
): HTMLElement {
  const wrap = document.createElement("div");
  wrap.style.display = "flex";
  wrap.style.alignItems = "center";
  wrap.style.justifyContent = "center";
  wrap.style.width = "32px";
  wrap.style.height = "32px";
  wrap.style.pointerEvents = "none";

  if (navigating) {
    const arrow = document.createElement("div");
    arrow.textContent = "▲";
    arrow.style.color = "#00ffff";
    arrow.style.fontSize = "24px";
    arrow.style.fontWeight = "700";
    arrow.style.lineHeight = "1";
    arrow.style.textShadow = "0 1px 4px rgba(0,0,0,0.85)";
    arrow.style.transform = mapRotates ? "rotate(0deg)" : `rotate(${heading ?? 0}deg)`;
    arrow.style.transformOrigin = "center center";
    wrap.appendChild(arrow);
  } else {
    const dot = document.createElement("div");
    dot.style.width = "18px";
    dot.style.height = "18px";
    dot.style.borderRadius = "50%";
    dot.style.background = "#00e5ff";
    dot.style.border = "2px solid #ffffff";
    dot.style.boxShadow = "0 0 10px rgba(0,229,255,0.85)";
    wrap.appendChild(dot);
  }

  return wrap;
}

export async function createNumberedPlaceMarker(
  position: google.maps.LatLngLiteral,
  map: google.maps.Map,
  index: number,
  title: string,
): Promise<google.maps.marker.AdvancedMarkerElement> {
  const { AdvancedMarkerElement, PinElement } = await loadMarkerLibrary();
  const pin = new PinElement({
    glyph: String(index + 1),
    glyphColor: "#0a0a0a",
    background: "#a855f7",
    borderColor: "#ffffff",
    scale: 1.05,
  });
  return new AdvancedMarkerElement({
    map,
    position,
    title,
    content: pin.element,
    zIndex: 100 + index,
  });
}

export async function createDestinationMarker(
  position: google.maps.LatLngLiteral,
  map: google.maps.Map,
  title: string,
): Promise<google.maps.marker.AdvancedMarkerElement> {
  const { AdvancedMarkerElement, PinElement } = await loadMarkerLibrary();
  const pin = new PinElement({
    background: "#a855f7",
    borderColor: "#ffffff",
    glyphColor: "#ffffff",
    scale: 1.15,
  });
  return new AdvancedMarkerElement({
    map,
    position,
    title,
    content: pin.element,
    zIndex: 200,
  });
}

export async function createUserLocationMarker(
  map: google.maps.Map,
  position: google.maps.LatLngLiteral,
): Promise<google.maps.marker.AdvancedMarkerElement> {
  const { AdvancedMarkerElement } = await loadMarkerLibrary();
  return new AdvancedMarkerElement({
    map,
    position,
    title: "Tu ubicación",
    content: createUserLocationContent(null, false, false),
    zIndex: 999,
  });
}
