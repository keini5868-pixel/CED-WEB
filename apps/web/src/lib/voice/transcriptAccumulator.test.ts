import { describe, expect, it } from "vitest";

import { resolveAgentTranscriptMerge } from "./transcriptAccumulator";

describe("resolveAgentTranscriptMerge", () => {
  it("does not glue two distinct agent replies without the same stream", () => {
    const first =
      "Es un frasco de proteína en polvo blanco con tapa negra. No veo marca legible.";
    const second =
      "En esta toma el frasco muestra el logo MyProtein y la etiqueta está más cerca.";
    const out = resolveAgentTranscriptMerge(first, second, { sameStream: false });
    expect(out.action).toBe("new");
    expect(out.text).toBe(second);
  });

  it("strips a repeated previous analysis glued in front of the new one", () => {
    const first =
      "Es un frasco de proteína en polvo blanco con tapa negra. No veo marca legible.";
    const glued = `${first} En esta toma el frasco muestra el logo MyProtein.`;
    const out = resolveAgentTranscriptMerge(first, glued, { sameStream: false });
    expect(out.action).toBe("new");
    expect(out.text).toContain("MyProtein");
    expect(out.text.startsWith("Es un frasco")).toBe(false);
  });

  it("merges streaming chunks on the same stream", () => {
    const out = resolveAgentTranscriptMerge("Es un frasco", "Es un frasco de proteína", {
      sameStream: true,
    });
    expect(out.action).toBe("merge");
    expect(out.text).toBe("Es un frasco de proteína");
  });

  it("does not glue two complete replies that share a stream key", () => {
    const first =
      "Es un frasco de proteína en polvo blanco con tapa negra. No veo marca legible.";
    const second =
      "En esta toma el frasco muestra el logo MyProtein y la etiqueta está más cerca.";
    const out = resolveAgentTranscriptMerge(first, second, {
      sameStream: false,
      incomingPartial: false,
      previousPartial: false,
    });
    expect(out.action).toBe("new");
    expect(out.text).toBe(second);
  });
});
