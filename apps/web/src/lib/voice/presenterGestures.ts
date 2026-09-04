/** El presentador (ROBOT) solo existe para el dueño / super admin. */
export function isPresenterRobotAllowed(isOwner: boolean): boolean {
  return isOwner === true;
}

export type PresenterGesture =
  | "idle"
  | "welcome"
  | "farewell"
  | "think"
  | "success"
  | "serious"
  | "laugh"
  | "listen"
  | "construct"
  | "error"
  | "ok"
  | "point";

export type GesturePose = {
  y: number;
  rx: number;
  ry: number;
  rz: number;
  scale: number;
  bobMul: number;
};

type GestureRule = {
  re: RegExp;
  gesture: PresenterGesture;
};

const SPEECH_RULES: GestureRule[] = [
  { re: /\b(jaja|jajaja|jeje|risa|gracioso|c[oó]mico)\b/i, gesture: "laugh" },
  { re: /\b(error|fall[oó]|confund|no entiendo|ay no)\b/i, gesture: "error" },
  { re: /\b(perfecto|listo|okey|ok|hecho|confirmad)\b/i, gesture: "ok" },
  { re: /\b(gracias|bienvenido|hola robot|buenas)\b/i, gesture: "welcome" },
  { re: /\b(adi[oó]s|chao|nos vemos|hasta luego)\b/i, gesture: "farewell" },
  { re: /\b(piensa|analiz|estudi|calcul|proces)\b/i, gesture: "think" },
  { re: /\b(dinero|ganancia|cierre|finanzas|venta)\b/i, gesture: "success" },
  { re: /\b(imagen|pdf|genera|constru|dise[nñ]a)\b/i, gesture: "construct" },
];

export function matchPresenterGesture(text: string): PresenterGesture | null {
  const t = (text || "").trim();
  if (t.length < 2) return null;
  for (const rule of SPEECH_RULES) {
    if (rule.re.test(t)) return rule.gesture;
  }
  return null;
}

export function gestureForHotspot(hotspot: string): PresenterGesture {
  if (hotspot === "finanzas" || hotspot === "nav-plans") return "success";
  if (hotspot === "avanzado") return "serious";
  if (hotspot === "nav-history" || hotspot === "nav-media") return "construct";
  if (hotspot === "asistente") return "farewell";
  return "point";
}

export function gestureForModule(moduleId: string | null | undefined): PresenterGesture | null {
  if (!moduleId) return null;
  if (moduleId === "image_gen" || moduleId === "pdf") return "construct";
  if (moduleId === "web_search" || moduleId === "prospection") return "think";
  if (moduleId === "finance") return "success";
  return null;
}

export function gestureForWorkspace(workspace: "chat" | "advanced" | "finance"): PresenterGesture | null {
  if (workspace === "advanced") return "serious";
  if (workspace === "finance") return "success";
  return null;
}

/** Ángulos de articulations holográficas (cabeza / torso / brazos) según gesto. */
export function gesturePose(gesture: PresenterGesture, t: number): GesturePose {
  switch (gesture) {
    case "think":
      return {
        y: -6 + Math.sin(t * 1.2) * 2,
        rx: -16,
        ry: 12 + Math.sin(t * 0.7) * 4,
        rz: -10,
        scale: 1,
        bobMul: 0.45,
      };
    case "success":
      return {
        y: -14 + Math.abs(Math.sin(t * 6)) * 10,
        rx: -8,
        ry: Math.sin(t * 8) * 16,
        rz: Math.sin(t * 7) * 8,
        scale: 1.06 + Math.abs(Math.sin(t * 6)) * 0.05,
        bobMul: 1.4,
      };
    case "serious":
      return {
        y: 4,
        rx: 4,
        ry: Math.sin(t * 0.5) * 3,
        rz: 0,
        scale: 0.98,
        bobMul: 0.2,
      };
    case "laugh":
      return {
        y: Math.sin(t * 14) * 7,
        rx: Math.sin(t * 16) * 8,
        ry: Math.sin(t * 11) * 14,
        rz: Math.sin(t * 13) * 10,
        scale: 1.04,
        bobMul: 1.6,
      };
    case "listen":
      return {
        y: 2,
        rx: 6,
        ry: -22,
        rz: 14 + Math.sin(t * 1.4) * 3,
        scale: 1,
        bobMul: 0.35,
      };
    case "construct":
      return {
        y: Math.sin(t * 3.2) * 5,
        rx: Math.sin(t * 4) * 6,
        ry: Math.sin(t * 5.5) * 22,
        rz: Math.sin(t * 3) * 4,
        scale: 1.02,
        bobMul: 0.7,
      };
    case "error":
      return {
        y: 10 + Math.sin(t * 9) * 3,
        rx: 8,
        ry: Math.sin(t * 2) * 6,
        rz: Math.sin(t * 10) * 7,
        scale: 0.92,
        bobMul: 0.5,
      };
    case "ok":
      return {
        y: -10,
        rx: -12,
        ry: 8,
        rz: -6,
        scale: 1.08,
        bobMul: 0.8,
      };
    case "welcome":
      return {
        y: -8 + Math.sin(t * 5) * 6,
        rx: -6,
        ry: Math.sin(t * 6) * 28,
        rz: Math.sin(t * 5) * 8,
        scale: 1.05,
        bobMul: 1.1,
      };
    case "farewell":
      return {
        y: 28,
        rx: 28,
        ry: 0,
        rz: 0,
        scale: 0.78,
        bobMul: 0.15,
      };
    case "point":
      return {
        y: -8,
        rx: -10,
        ry: 18,
        rz: -8,
        scale: 1.02,
        bobMul: 0.6,
      };
    default:
      return { y: 0, rx: 0, ry: 0, rz: 0, scale: 1, bobMul: 1 };
  }
}
