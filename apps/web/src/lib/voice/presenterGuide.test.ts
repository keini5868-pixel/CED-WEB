import { describe, expect, it } from "vitest";

import { matchPresenterGuide } from "./presenterGuide";

describe("matchPresenterGuide", () => {
  it("va a Sistema y abre el menú", () => {
    expect(matchPresenterGuide("esta es la pestaña de sistema")).toEqual([
      { hotspot: "sistema", click: true },
    ]);
  });

  it("planes abre Sistema y luego Planes", () => {
    expect(matchPresenterGuide("aquí están los planes")).toEqual([
      { hotspot: "sistema", click: true },
      { hotspot: "nav-plans", click: true },
    ]);
  });

  it("no dispara en frases cortas", () => {
    expect(matchPresenterGuide("ok")).toBeNull();
  });
});
