/** Ícono visual según maniobra de Routes API (estilo Google Maps). */
export function maneuverIcon(maneuver: string | undefined | null): string {
  const m = String(maneuver || "straight").toUpperCase().replace(/-/g, "_");

  if (m.includes("SHARP") && m.includes("LEFT")) return "⬅";
  if (m.includes("SHARP") && m.includes("RIGHT")) return "➡";
  if (m.includes("SLIGHT") && m.includes("LEFT")) return "↖";
  if (m.includes("SLIGHT") && m.includes("RIGHT")) return "↗";
  if (m.includes("ROUNDABOUT") && m.includes("LEFT")) return "↺";
  if (m.includes("ROUNDABOUT") && m.includes("RIGHT")) return "↻";
  if (m.includes("ROUNDABOUT")) return "↻";
  if (m.includes("LEFT")) return "←";
  if (m.includes("RIGHT")) return "→";
  if (m.includes("UTURN") || m.includes("U_TURN")) return "↩";
  return "↑";
}

export function formatMiles(meters: number): string {
  const miles = meters / 1609.344;
  if (miles < 0.1) return "0.1 mi";
  return `${miles.toFixed(1)} mi`;
}

export function formatArrivalTime(remainingSeconds: number): string {
  const eta = new Date(Date.now() + Math.max(0, remainingSeconds) * 1000);
  return eta.toLocaleTimeString("es", { hour: "numeric", minute: "2-digit" });
}

export function estimateRemaining(
  routeDistanceM: number,
  routeDurationS: number,
  remainingM: number,
): { minutes: number; seconds: number } {
  if (routeDistanceM <= 0 || remainingM <= 0) {
    return { minutes: 0, seconds: 0 };
  }
  const ratio = Math.min(1, remainingM / routeDistanceM);
  const totalSec = Math.max(0, Math.round(routeDurationS * ratio));
  return { minutes: Math.floor(totalSec / 60), seconds: totalSec };
}
