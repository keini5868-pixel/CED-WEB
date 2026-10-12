import { describe, expect, it } from "vitest";

import { parseCameraIntent } from "./cameraIntents";

describe("parseCameraIntent", () => {
  it("opens only on an explicit camera phrase", () => {
    expect(parseCameraIntent("activa la cámara")).toBe("activate");
    expect(parseCameraIntent("mira esto")).toBe("activate");
  });

  it("does not treat stop as camera", () => {
    for (const phrase of [
      "stop",
      "estop",
      "etop",
      "esto",
      "es todo",
      "okay set stop",
      "alto",
      "cállate",
    ]) {
      expect(parseCameraIntent(phrase)).toBeNull();
    }
  });
});
