import { describe, expect, it } from "vitest";

import {
  gestureForHotspot,
  gestureForModule,
  gestureForWorkspace,
  gestureRig,
  isPresenterRobotAllowed,
  matchPresenterGesture,
  reactToSpeech,
} from "./presenterGestures";

describe("matchPresenterGesture", () => {
  it("risa y confirmación", () => {
    expect(matchPresenterGesture("jaja qué gracioso")).toBe("laugh");
    expect(matchPresenterGesture("perfecto, listo")).toBe("ok");
  });

  it("reacciona a la conversación de una presentación", () => {
    expect(matchPresenterGesture("cierra las pestañas")).toBe("ok");
    expect(matchPresenterGesture("abre sistema")).toBe("present");
    expect(matchPresenterGesture("mira esto")).toBe("look");
    expect(reactToSpeech("cómo funciona esto")).toBe("think");
  });
});

describe("gesture context", () => {
  it("finanzas celebra y avanzado se pone a pensar", () => {
    expect(gestureForHotspot("finanzas")).toBe("success");
    expect(gestureForHotspot("avanzado")).toBe("think");
    expect(gestureForWorkspace("finance")).toBe("success");
    expect(gestureForWorkspace("advanced")).toBe("think");
  });

  it("módulos de imagen disparan construcción", () => {
    expect(gestureForModule("image_gen")).toBe("construct");
    expect(gestureForModule("pdf")).toBe("construct");
    expect(gestureForModule("web_search")).toBe("think");
  });

  it("saludo levanta la mano a la sien", () => {
    const rig = gestureRig("welcome", 0.2);
    expect(rig.rArm).toBeLessThan(-100);
    expect(rig.rHand).toBe("palm");
    expect(rig.mouth).toBe("grin");
  });

  it("las 5 poses de referencia mueven brazos y manos", () => {
    const think = gestureRig("think", 0);
    expect(think.rHand).toBe("cup");
    expect(think.mouth).toBe("flat");
    const win = gestureRig("success", 0);
    expect(win.lArm).toBeGreaterThan(140);
    expect(win.rArm).toBeLessThan(-140);
    expect(win.eyes).toBe("happy");
    const shrug = gestureRig("error", 0);
    expect(shrug.prop).toBe("question");
    expect(shrug.lHand).toBe("palm");
    const ok = gestureRig("ok", 0);
    expect(ok.rHand).toBe("thumb");
  });

  it("el robot solo existe para el dueño", () => {
    expect(isPresenterRobotAllowed(false)).toBe(false);
    expect(isPresenterRobotAllowed(true)).toBe(true);
  });
});
