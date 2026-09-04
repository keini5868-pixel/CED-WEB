import { describe, expect, it } from "vitest";

import {
  gestureForHotspot,
  gestureForModule,
  gestureForWorkspace,
  isPresenterRobotAllowed,
  matchPresenterGesture,
} from "./presenterGestures";

describe("matchPresenterGesture", () => {
  it("risa y confirmación", () => {
    expect(matchPresenterGesture("jaja qué gracioso")).toBe("laugh");
    expect(matchPresenterGesture("perfecto, listo")).toBe("ok");
  });

  it("análisis y construcción", () => {
    expect(matchPresenterGesture("analiza este producto")).toBe("think");
    expect(matchPresenterGesture("genera una imagen")).toBe("construct");
  });
});

describe("gesture context", () => {
  it("finanzas celebra y avanzado se pone serio", () => {
    expect(gestureForHotspot("finanzas")).toBe("success");
    expect(gestureForHotspot("avanzado")).toBe("serious");
    expect(gestureForWorkspace("finance")).toBe("success");
    expect(gestureForWorkspace("advanced")).toBe("serious");
  });

  it("módulos de imagen disparan construcción", () => {
    expect(gestureForModule("image_gen")).toBe("construct");
    expect(gestureForModule("pdf")).toBe("construct");
    expect(gestureForModule("web_search")).toBe("think");
  });

  it("el robot solo existe para el dueño", () => {
    expect(isPresenterRobotAllowed(false)).toBe(false);
    expect(isPresenterRobotAllowed(true)).toBe(true);
  });
});
