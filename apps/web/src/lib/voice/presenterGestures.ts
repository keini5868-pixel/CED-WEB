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
  | "point"
  | "present"
  | "sad"
  | "stress"
  | "zen"
  | "look";

export type GesturePose = {
  y: number;
  rx: number;
  ry: number;
  rz: number;
  scale: number;
  bobMul: number;
};

export type MouthShape = "smile" | "grin" | "oh" | "flat" | "sad";
export type HandShape = "fingers" | "palm" | "thumb" | "cup";
export type EyeShape = "open" | "happy" | "narrow" | "sad";

export type GestureRig = {
  lArm: number;
  lElbow: number;
  rArm: number;
  rElbow: number;
  lHand: HandShape;
  rHand: HandShape;
  lWrist: number;
  rWrist: number;
  headTilt: number;
  headNod: number;
  eyeY: number;
  lookX: number;
  lookY: number;
  eyes: EyeShape;
  mouth: MouthShape;
  brow: number;
  glow: number;
  prop: "none" | "question";
};

type GestureRule = {
  re: RegExp;
  gesture: PresenterGesture;
};

const SPEECH_RULES: GestureRule[] = [
  { re: /\b(jaja|jajaja|jeje|risa|gracioso|c[oó]mico)\b/i, gesture: "laugh" },
  { re: /\b(error|fall[oó]|confund|no entiendo|no s[eé]|ay no|qu[eé]\?)\b/i, gesture: "error" },
  { re: /\b(perd[oó]n|lo siento|triste|fall[eé]|no pude)\b/i, gesture: "sad" },
  { re: /\b(estr[eé]s|auxilio|urgencia| explota|se rompi[oó])\b/i, gesture: "stress" },
  { re: /\b(perfecto|listo|okey|\bok\b|hecho|confirmad|pulgar|correcto)\b/i, gesture: "ok" },
  { re: /\b(gracias|bienvenido|hola robot|buenas|saluda)\b/i, gesture: "welcome" },
  { re: /\b(adi[oó]s|chao|nos vemos|hasta luego)\b/i, gesture: "farewell" },
  { re: /\b(piensa|analiz|estudi|calcul|proces|espera un momento)\b/i, gesture: "think" },
  { re: /\b(espera|calma|respira|medita|zen)\b/i, gesture: "zen" },
  { re: /\b(mira|observa|f[ií]jate|all[aá]|aqu[ií] est[aá])\b/i, gesture: "look" },
  { re: /\b(te presento|esta es|aqu[ií] tienes|mu[eé]strale|ense[nñ]a)\b/i, gesture: "present" },
  { re: /\b(dinero|ganancia|finanzas|venta|genial|excelente|vamos)\b/i, gesture: "success" },
  { re: /\b(imagen|pdf|genera|constru|dise[nñ]a)\b/i, gesture: "construct" },
  { re: /\b(cierra|cerrar|cierre|oculta)\b/i, gesture: "ok" },
  { re: /\b(abre|abrir|pesta[nñ]a|sistema)\b/i, gesture: "present" },
];

export function matchPresenterGesture(text: string): PresenterGesture | null {
  const t = (text || "").trim();
  if (t.length < 2) return null;
  for (const rule of SPEECH_RULES) {
    if (rule.re.test(t)) return rule.gesture;
  }
  return null;
}

/** Reacci[o]n de presentaci[o]n: siempre hay un gesto, no solo keywords exactas. */
export function reactToSpeech(text: string): PresenterGesture {
  const hit = matchPresenterGesture(text);
  if (hit) return hit;
  const t = (text || "").trim();
  if (/\?/.test(t) || /\b(qu[eé]|c[oó]mo|por qu[eé]|cu[aá]ndo|d[oó]nde)\b/i.test(t)) {
    return "think";
  }
  if (t.length > 70) return "think";
  if (t.length >= 4) return "listen";
  return "idle";
}

export function gestureForHotspot(hotspot: string): PresenterGesture {
  if (hotspot === "finanzas" || hotspot === "nav-plans") return "success";
  if (hotspot === "avanzado") return "think";
  if (hotspot === "nav-history" || hotspot === "nav-media") return "construct";
  if (hotspot === "asistente") return "farewell";
  if (hotspot === "sistema" || hotspot === "home") return "welcome";
  if (hotspot === "module-close") return "ok";
  if (hotspot === "viability" || hotspot === "trends") return "think";
  if (hotspot === "opportunities" || hotspot === "team") return "present";
  return "present";
}

export function gestureForModule(moduleId: string | null | undefined): PresenterGesture | null {
  if (!moduleId) return null;
  if (moduleId === "image_gen" || moduleId === "pdf") return "construct";
  if (moduleId === "web_search" || moduleId === "prospection") return "think";
  if (moduleId === "finance") return "success";
  return "ok";
}

export function gestureForWorkspace(workspace: "chat" | "advanced" | "finance"): PresenterGesture | null {
  if (workspace === "advanced") return "think";
  if (workspace === "finance") return "success";
  return null;
}

function hands(
  extra: Partial<GestureRig> & Pick<GestureRig, "lArm" | "rArm" | "mouth">,
): GestureRig {
  return {
    lElbow: 12,
    rElbow: 12,
    lHand: "fingers",
    rHand: "fingers",
    lWrist: 0,
    rWrist: 0,
    headTilt: 0,
    headNod: 0,
    eyeY: 1,
    lookX: 0,
    lookY: 0,
    eyes: "open",
    brow: 0,
    glow: 0.95,
    prop: "none",
    ...extra,
  };
}

/** Ángulos de articulations holográficas (cabeza / torso / brazos) según gesto. */
export function gesturePose(gesture: PresenterGesture, t: number): GesturePose {
  switch (gesture) {
    case "think":
      return {
        y: -4 + Math.sin(t * 1.1) * 2,
        rx: -8,
        ry: 10 + Math.sin(t * 0.7) * 3,
        rz: -8,
        scale: 1,
        bobMul: 0.4,
      };
    case "success":
    case "laugh":
      return {
        y: -18 + Math.abs(Math.sin(t * 5.5)) * 12,
        rx: -6,
        ry: Math.sin(t * 6) * 10,
        rz: Math.sin(t * 5) * 6,
        scale: 1.08 + Math.abs(Math.sin(t * 5.5)) * 0.04,
        bobMul: 1.5,
      };
    case "serious":
      return {
        y: 2,
        rx: 2,
        ry: Math.sin(t * 0.5) * 3,
        rz: 0,
        scale: 0.98,
        bobMul: 0.25,
      };
    case "listen":
      return {
        y: 2,
        rx: 4,
        ry: -8,
        rz: 8 + Math.sin(t * 1.4) * 2,
        scale: 1,
        bobMul: 0.3,
      };
    case "construct":
      return {
        y: Math.sin(t * 3.2) * 4,
        rx: Math.sin(t * 4) * 4,
        ry: Math.sin(t * 5.5) * 12,
        rz: Math.sin(t * 3) * 3,
        scale: 1.02,
        bobMul: 0.65,
      };
    case "error":
      return {
        y: 6 + Math.sin(t * 2.2) * 3,
        rx: 4,
        ry: Math.sin(t * 1.6) * 8,
        rz: Math.sin(t * 2) * 4,
        scale: 0.98,
        bobMul: 0.55,
      };
    case "ok":
      return {
        y: -8,
        rx: -6,
        ry: -10,
        rz: 4,
        scale: 1.06,
        bobMul: 0.7,
      };
    case "welcome":
    case "farewell":
      return {
        y: -6 + Math.sin(t * 4) * 4,
        rx: -4,
        ry: Math.sin(t * 3) * 8,
        rz: Math.sin(t * 4) * 5,
        scale: 1.04,
        bobMul: 0.9,
      };
    case "point":
      return {
        y: -6,
        rx: -6,
        ry: 12,
        rz: -6,
        scale: 1.02,
        bobMul: 0.5,
      };
    case "present":
      return {
        y: -8,
        rx: -8,
        ry: 16,
        rz: -4,
        scale: 1.05,
        bobMul: 0.7,
      };
    case "sad":
      return {
        y: 10,
        rx: 12,
        ry: 0,
        rz: 0,
        scale: 0.92,
        bobMul: 0.2,
      };
    case "stress":
      return {
        y: 4 + Math.sin(t * 10) * 3,
        rx: 6,
        ry: Math.sin(t * 9) * 8,
        rz: Math.sin(t * 11) * 6,
        scale: 0.96,
        bobMul: 0.8,
      };
    case "zen":
      return {
        y: -2 + Math.sin(t * 0.8) * 3,
        rx: 0,
        ry: 0,
        rz: 0,
        scale: 1,
        bobMul: 0.15,
      };
    case "look":
      return {
        y: -10,
        rx: -12,
        ry: 18,
        rz: 4,
        scale: 1.04,
        bobMul: 0.45,
      };
    default:
      return { y: 0, rx: 0, ry: 0, rz: 0, scale: 1, bobMul: 1 };
  }
}

/**
 * Poses frente a cámara. Brazo izquierdo del SVG = derecha del robot.
 * 0° = brazo caído. + = afuera/arriba a la izquierda. − = afuera/arriba a la derecha.
 */
export function gestureRig(gesture: PresenterGesture, t: number): GestureRig {
  switch (gesture) {
    case "think":
      return hands({
        lArm: 18,
        lElbow: 10,
        lHand: "fingers",
        rArm: 118 + Math.sin(t * 1.4) * 6,
        rElbow: 78,
        rHand: "cup",
        rWrist: -20,
        headTilt: 16,
        headNod: -10,
        lookX: 2,
        lookY: -7,
        eyes: "narrow",
        mouth: "flat",
        brow: 6,
        glow: 0.82,
      });
    case "success":
    case "laugh":
      return hands({
        lArm: 168 + Math.sin(t * 8) * 8,
        lElbow: 18,
        lHand: "palm",
        rArm: -168 + Math.sin(t * 8 + 1) * 8,
        rElbow: 18,
        rHand: "palm",
        headTilt: Math.sin(t * 7) * 6,
        headNod: -12,
        eyes: "happy",
        eyeY: 0.2,
        mouth: "grin",
        brow: -6,
        glow: 1.25,
      });
    case "error":
      return hands({
        lArm: 78 + Math.sin(t * 2) * 6,
        lElbow: -42,
        lHand: "palm",
        lWrist: -70,
        rArm: -78 - Math.sin(t * 2) * 6,
        rElbow: 42,
        rHand: "palm",
        rWrist: 70,
        headTilt: Math.sin(t * 1.8) * 8,
        headNod: 6,
        eyes: "open",
        lookY: 2,
        mouth: "sad",
        brow: 8,
        glow: 0.7,
        prop: "question",
      });
    case "ok":
      return hands({
        lArm: 18,
        lElbow: 10,
        lHand: "fingers",
        rArm: -96,
        rElbow: -88,
        rHand: "thumb",
        rWrist: 12,
        headTilt: -6,
        headNod: -6,
        eyes: "happy",
        mouth: "smile",
        brow: -2,
        glow: 1.05,
      });
    case "welcome":
      return hands({
        lArm: 18,
        lElbow: 8,
        rArm: -148 + Math.sin(t * 7) * 10,
        rElbow: 42,
        rHand: "palm",
        rWrist: 8,
        headTilt: Math.sin(t * 5) * 8,
        headNod: -6,
        eyes: "open",
        mouth: "grin",
        brow: -2,
        glow: 1,
      });
    case "farewell":
      return hands({
        lArm: 148 + Math.sin(t * 7) * 10,
        lElbow: 38,
        lHand: "palm",
        rArm: 12,
        rElbow: 10,
        headTilt: 4,
        headNod: 8,
        eyes: "open",
        mouth: "smile",
        glow: 0.65,
      });
    case "listen":
      return hands({
        lArm: 18,
        lElbow: 8,
        rArm: -132,
        rElbow: 58,
        rHand: "cup",
        rWrist: 18,
        headTilt: 14 + Math.sin(t * 1.3) * 3,
        headNod: 2,
        lookX: 4,
        eyes: "open",
        mouth: "oh",
        brow: 3,
        glow: 0.88,
      });
    case "serious":
      return hands({
        lArm: 22,
        lElbow: 8,
        rArm: 108,
        rElbow: 72,
        rHand: "cup",
        headTilt: 8,
        headNod: 4,
        eyes: "narrow",
        mouth: "flat",
        brow: 8,
        glow: 0.72,
      });
    case "construct":
      return hands({
        lArm: -48 + Math.sin(t * 5) * 18,
        lElbow: 52 + Math.sin(t * 6) * 10,
        lHand: "cup",
        rArm: 48 + Math.sin(t * 5 + 2) * 18,
        rElbow: 52 + Math.sin(t * 6 + 1) * 10,
        rHand: "cup",
        headTilt: Math.sin(t * 3) * 4,
        headNod: -4,
        lookY: -3,
        mouth: "oh",
        brow: 4,
        glow: 1.12,
      });
    case "point":
      return hands({
        lArm: 16,
        lElbow: 8,
        rArm: -118,
        rElbow: -8,
        rHand: "fingers",
        rWrist: -18,
        headTilt: 8,
        headNod: -8,
        lookX: 6,
        lookY: -4,
        mouth: "smile",
        brow: 2,
        glow: 1.05,
      });
    case "present":
      return hands({
        lArm: 22,
        lElbow: 10,
        rArm: -72,
        rElbow: -12,
        rHand: "palm",
        rWrist: -24,
        headTilt: 6,
        headNod: -8,
        lookX: 8,
        lookY: -3,
        mouth: "grin",
        brow: -2,
        glow: 1.1,
      });
    case "sad":
      return hands({
        lArm: 48,
        lElbow: 70,
        lHand: "cup",
        rArm: -48,
        rElbow: 70,
        rHand: "cup",
        headTilt: 0,
        headNod: 16,
        eyes: "sad",
        lookY: 4,
        mouth: "sad",
        brow: 6,
        glow: 0.55,
      });
    case "stress":
      return hands({
        lArm: 150,
        lElbow: 70,
        lHand: "cup",
        rArm: -150,
        rElbow: 70,
        rHand: "cup",
        headTilt: Math.sin(t * 12) * 8,
        headNod: 4,
        eyes: "sad",
        mouth: "sad",
        brow: 10,
        glow: 0.6,
      });
    case "zen":
      return hands({
        lArm: 32,
        lElbow: 18,
        lHand: "palm",
        rArm: -32,
        rElbow: 18,
        rHand: "palm",
        headTilt: 0,
        headNod: -2,
        eyes: "happy",
        eyeY: 0.25,
        mouth: "smile",
        glow: 0.8,
      });
    case "look":
      return hands({
        lArm: 14,
        lElbow: 8,
        rArm: -100,
        rElbow: 88,
        rHand: "cup",
        rWrist: 10,
        headTilt: -8,
        headNod: -12,
        lookX: 8,
        lookY: -6,
        mouth: "oh",
        brow: 4,
        glow: 1.05,
      });
    default:
      return hands({
        lArm: 14 + Math.sin(t * 1.6) * 16,
        lElbow: 10 + Math.sin(t * 1.4) * 6,
        rArm: -14 - Math.sin(t * 1.6) * 16,
        rElbow: 10 - Math.sin(t * 1.4) * 6,
        headTilt: Math.sin(t * 0.9) * 5,
        headNod: Math.sin(t * 1.1) * 3,
        eyeY: Math.sin(t * 0.35) > 0.92 ? 0.12 : 1,
        lookX: Math.sin(t * 0.6) * 2,
        mouth: "smile",
        glow: 0.9,
      });
  }
}
