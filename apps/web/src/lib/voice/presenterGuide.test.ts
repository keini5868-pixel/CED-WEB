import { describe, expect, it } from "vitest";

import { matchPresenterGuide } from "./presenterGuide";

describe("matchPresenterGuide", () => {
  it("va a Sistema y abre el menú", () => {
    expect(matchPresenterGuide("esta es la pestaña de sistema")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
    ]);
  });

  it("planes abre Sistema y luego Planes", () => {
    expect(matchPresenterGuide("aquí están los planes")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-plans", click: true },
    ]);
  });

  it("cierra todo y cierra Sistema", () => {
    expect(matchPresenterGuide("cerrar")).toEqual([{ action: "close-all" }]);
    expect(matchPresenterGuide("cierra todo")).toEqual([{ action: "close-all" }]);
    expect(matchPresenterGuide("sierra")).toEqual([{ action: "close-all" }]);
    expect(matchPresenterGuide("cierra las pestañas que abre")).toEqual([{ action: "close-all" }]);
    expect(matchPresenterGuide("cierra sistema")).toEqual([{ action: "close-all" }]);
  });

  it("cierra oportunidades por nombre, no todo el HUD", () => {
    expect(matchPresenterGuide("cierra oportunidades")).toEqual([
      { hotspot: "module-close", click: true, force: "close" },
      { action: "close-module" },
    ]);
    expect(matchPresenterGuide("cierra oportunidad PM")).toEqual([
      { hotspot: "module-close", click: true, force: "close" },
      { action: "close-module" },
    ]);
  });
});
