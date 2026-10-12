import { describe, expect, it } from "vitest";

import { isCameraOpenUtterance, parseCameraIntent } from "./cameraIntents";

describe("parseCameraIntent", () => {
  it("opens only on CED enciende la cámara", () => {
    expect(parseCameraIntent("CED enciende la cámara")).toBe("activate");
    expect(parseCameraIntent("ok ced enciende la camara")).toBe("activate");
    expect(parseCameraIntent("okay set enciende la cámara")).toBe("activate");
    expect(isCameraOpenUtterance("CED enciende la cámara")).toBe(true);
  });

  it("does not open on other phrases", () => {
    for (const phrase of [
      "activa la cámara",
      "abre la cámara",
      "mira esto",
      "qué ves",
      "stop",
      "stopo",
      "stop o",
      "estop",
      "GRABAR",
      "enciende la cámara",
    ]) {
      expect(parseCameraIntent(phrase)).not.toBe("activate");
    }
  });
});
