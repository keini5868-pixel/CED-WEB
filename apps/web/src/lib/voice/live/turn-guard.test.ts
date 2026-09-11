import { describe, expect, it } from "vitest";

import {
  isSameVoiceUtterance,
  shouldSkipAlreadyAnswered,
} from "./turn-guard";

describe("isSameVoiceUtterance", () => {
  it("trata la misma pregunta con puntuación distinta como igual", () => {
    expect(
      isSameVoiceUtterance("Háblame de FitLine.", "hablame de fitline"),
    ).toBe(true);
  });

  it("no mezcla un pedido nuevo con el anterior", () => {
    expect(
      isSameVoiceUtterance(
        "Háblame de FitLine",
        "generame una imagen de un gato",
      ),
    ).toBe(false);
  });
});

describe("shouldSkipAlreadyAnswered", () => {
  it("bloquea el retrigger del mismo turno dentro de la ventana", () => {
    expect(
      shouldSkipAlreadyAnswered({
        incoming: "háblame de FitLine",
        lastAnswered: "Háblame de FitLine.",
        lastAnsweredAt: 1_000,
        now: 4_000,
      }),
    ).toBe(true);
  });

  it("permite repetir la pregunta después del cooldown", () => {
    expect(
      shouldSkipAlreadyAnswered({
        incoming: "háblame de FitLine",
        lastAnswered: "Háblame de FitLine.",
        lastAnsweredAt: 1_000,
        now: 30_000,
      }),
    ).toBe(false);
  });
});
