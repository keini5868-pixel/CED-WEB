/**
 * Simulación de seguimiento de cámara en navegación (verificación del fix).
 * Trayecto de ~4 min sobre ruta curva con GPS ruidoso a 1 Hz.
 * Compara heading viejo (alternancia GPS/ruta + look-ahead % path) vs nuevo.
 *
 * Uso: pnpm dlx tsx scripts/sim_nav_camera.ts
 */

import {
  bearingDegrees,
  distanceMeters,
  navigationFollowZoom,
  navigationHeading,
  offsetByMeters,
  pointAlongPath,
  smoothHeading,
  smoothZoom,
  trackRouteProgress,
} from "../src/lib/navigation/geo";
import type { NavLatLng } from "../src/lib/api/navigation";

// ---- Ruta sintética: recta 500m → curva 90° (radio ~200m) → recta 600m (tipo Johnston Rd)
function buildRoute(): NavLatLng[] {
  const pts: NavLatLng[] = [];
  let p: NavLatLng = { lat: 35.06, lng: -80.85 };
  let brg = 20; // rumbo inicial
  const push = (dist: number, step = 12) => {
    for (let d = 0; d < dist; d += step) {
      p = offsetByMeters(p, brg, step);
      pts.push({ ...p });
    }
  };
  push(500);
  for (let i = 0; i < 30; i += 1) {
    brg += 3; // 90° en ~30 segmentos
    push(10, 10);
  }
  push(600);
  return pts;
}

// Determinista — mismo ruido en cada corrida.
let seed = 42;
function rand(): number {
  seed = (seed * 1103515245 + 12345) % 2 ** 31;
  return seed / 2 ** 31;
}
function gauss(sigma: number): number {
  return (rand() + rand() + rand() - 1.5) * 2 * sigma;
}

// Heading VIEJO (lógica anterior, reproducida para comparar)
function oldNavigationHeading(
  position: NavLatLng,
  path: NavLatLng[],
  gpsHeading: number | null,
  speed: number,
): number {
  let routeHeading: number | null = null;
  if (path.length >= 2) {
    const prog = trackRouteProgress(path, position, null);
    const idx = prog.idx;
    const lookIdx = Math.min(
      idx + Math.max(2, Math.floor(path.length * 0.01) + 2),
      path.length - 1,
    );
    const next = path[lookIdx] ?? path[path.length - 1]!;
    if (next.lat !== prog.snapped.lat || next.lng !== prog.snapped.lng) {
      routeHeading = bearingDegrees(prog.snapped, next);
    }
  }
  if (speed > 3.5 && gpsHeading != null) return gpsHeading;
  if (routeHeading != null) return routeHeading;
  return gpsHeading ?? 0;
}

function angDelta(a: number, b: number): number {
  return Math.abs(((b - a + 540) % 360) - 180);
}

function main() {
  const path = buildRoute();

  // Vehículo: avanza por la ruta a velocidad variable (11-16 m/s con frenada en curva a 3 m/s)
  let travelled = 0;
  const cam = { heading: null as number | null, zoom: null as number | null, routeIdx: null as number | null };
  let oldSmoothed: number | null = null;

  let maxJumpNew = 0;
  let maxJumpOld = 0;
  let jumpsNew = 0;
  let jumpsOld = 0;
  let maxZoomJump = 0;
  let prevZoom: number | null = null;
  let maxCenterDrift = 0;
  let prevNewHeading: number | null = null;
  let prevOldHeading: number | null = null;
  let idxRegressions = 0;
  let lastIdx = -1;

  const totalLen = path.reduce(
    (acc, p, i) => (i ? acc + distanceMeters(path[i - 1]!, p) : 0),
    0,
  );

  for (let t = 0; travelled < totalLen - 30; t += 1) {
    // Perfil de velocidad: frena en la curva (t 40-75), acelera después
    const speed = t > 40 && t < 75 ? 3 + 2 * rand() : 12 + 4 * rand();
    travelled += speed;

    const truth = pointAlongPath(path, 0, path[0]!, travelled);
    // GPS: ruido posicional 3-8 m; heading GPS ruidoso ±25° (y a veces basura 0)
    const noisy = offsetByMeters(truth, rand() * 360, 3 + 5 * rand());
    const idxT = trackRouteProgress(path, truth, null).idx;
    const trueHeading =
      idxT < path.length - 1 ? bearingDegrees(path[idxT]!, path[idxT + 1]!) : 20;
    const gpsHeading = rand() < 0.1 ? 0 : (trueHeading + gauss(25) + 360) % 360;

    // --- NUEVO pipeline (igual que followNavigationCamera)
    const prog = trackRouteProgress(path, noisy, cam.routeIdx);
    // Jitter pequeño al frenar es normal (ventana ±8); lo grave son saltos largos.
    if (prog.idx < lastIdx - 5) idxRegressions += 1;
    lastIdx = prog.idx;
    const rawNew = navigationHeading(noisy, path, gpsHeading, speed, cam.routeIdx);
    const newHeading = smoothHeading(cam.heading, rawNew, 30);
    cam.heading = newHeading;
    cam.routeIdx = prog.idx;
    const zoom = smoothZoom(cam.zoom, navigationFollowZoom(speed));
    cam.zoom = zoom;

    // --- VIEJO pipeline (con triple aplicación de smooth por los 3 efectos)
    const rawOld = oldNavigationHeading(noisy, path, gpsHeading, speed);
    let oldH = smoothHeading(oldSmoothed, rawOld, 45);
    oldH = smoothHeading(oldH, rawOld, 45); // efecto 2
    oldH = smoothHeading(oldH, rawOld, 45); // efecto 3
    oldSmoothed = oldH;

    if (prevNewHeading != null) {
      const dNew = angDelta(prevNewHeading, newHeading);
      maxJumpNew = Math.max(maxJumpNew, dNew);
      if (dNew > 35) jumpsNew += 1;
    }
    if (prevOldHeading != null) {
      const dOld = angDelta(prevOldHeading, oldH);
      maxJumpOld = Math.max(maxJumpOld, dOld);
      if (dOld > 35) jumpsOld += 1;
    }
    prevNewHeading = newHeading;
    prevOldHeading = oldH;

    if (prevZoom != null) maxZoomJump = Math.max(maxZoomJump, Math.abs(zoom - prevZoom));
    prevZoom = zoom;

    // Centro: el snapped no debe alejarse de la posición real
    const snapped = prog.offRouteM <= 35 ? prog.snapped : noisy;
    maxCenterDrift = Math.max(maxCenterDrift, distanceMeters(truth, snapped));
  }

  console.log("=== Simulación trayecto ~4 min, GPS ruidoso 1 Hz, curva 90° ===");
  console.log(`VIEJO: salto max heading/tick = ${maxJumpOld.toFixed(1)}°, ticks con salto >35° = ${jumpsOld}`);
  console.log(`NUEVO: salto max heading/tick = ${maxJumpNew.toFixed(1)}°, ticks con salto >35° = ${jumpsNew}`);
  console.log(`NUEVO: salto max zoom/tick = ${maxZoomJump.toFixed(2)} (viejo: hasta 0.80 instantáneo)`);
  console.log(`NUEVO: drift max del ancla vs posición real = ${maxCenterDrift.toFixed(1)} m`);
  console.log(`NUEVO: regresiones de índice de ruta = ${idxRegressions}`);

  const pass =
    maxJumpNew <= 31 && jumpsNew === 0 && maxZoomJump <= 0.26 && maxCenterDrift < 15 && idxRegressions === 0;
  console.log(pass ? "RESULTADO: PASS" : "RESULTADO: FAIL");
  process.exit(pass ? 0 : 1);
}

main();
