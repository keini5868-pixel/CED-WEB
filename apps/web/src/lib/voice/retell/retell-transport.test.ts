import { describe, expect, it } from "vitest";

import { inferRetellTransport, mapRetellClientError } from "./retell-transport";

function jwt(payload: Record<string, unknown>): string {
  const body = btoa(JSON.stringify(payload))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `eyJhbGciOiJub25lIn0.${body}.sig`;
}

describe("inferRetellTransport", () => {
  it("usa gateway cuando el JWT trae inst y no hay room LiveKit", () => {
    expect(
      inferRetellTransport({
        accessToken: jwt({
          sub: "client",
          inst: "i-01adc7920a8b4b62f",
          video: { canPublish: true, roomJoin: true },
        }),
      }),
    ).toBe("gateway");
  });

  it("respeta el transport que manda la API", () => {
    expect(
      inferRetellTransport({
        transport: "livekit",
        accessToken: jwt({ inst: "i-x" }),
      }),
    ).toBe("livekit");
  });
});

describe("mapRetellClientError", () => {
  it("traduce Error starting call", () => {
    expect(mapRetellClientError("Error starting call")).toMatch(/micrófono/i);
  });
});
