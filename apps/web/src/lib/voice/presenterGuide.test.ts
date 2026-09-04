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

  it("activa el asistente de voz y apaga el robot", () => {
    expect(matchPresenterGuide("activa asistente de voz")).toEqual([{ action: "start-assist" }]);
    expect(matchPresenterGuide("activa asistente de vos")).toEqual([{ action: "start-assist" }]);
    expect(matchPresenterGuide("activa el asistente de voz")).toEqual([{ action: "start-assist" }]);
    expect(matchPresenterGuide("abre el asistente")).toEqual([{ action: "start-assist" }]);
    expect(matchPresenterGuide("enciende el asistente")).toEqual([{ action: "start-assist" }]);
    expect(matchPresenterGuide("cierra el asistente")).not.toEqual([{ action: "start-assist" }]);
  });

  it("regresa al panel principal desde Historial u otras pantallas", () => {
    expect(matchPresenterGuide("regresa a panel principal")).toEqual([{ action: "go-home" }]);
    expect(matchPresenterGuide("volver al panel principal")).toEqual([{ action: "go-home" }]);
  });

  it("abre cada opción del HUD por su nombre", () => {
    expect(matchPresenterGuide("abre oportunidades")).toEqual([{ hotspot: "opportunities", click: true }]);
    expect(matchPresenterGuide("abre análisis de producto")).toEqual([{ hotspot: "viability", click: true }]);
    expect(matchPresenterGuide("abre tendencia")).toEqual([{ hotspot: "trends", click: true }]);
    expect(matchPresenterGuide("abre estructura PM")).toEqual([{ hotspot: "team", click: true }]);
    expect(matchPresenterGuide("abre avanzado")).toEqual([{ hotspot: "avanzado", click: true }]);
    expect(matchPresenterGuide("abre finanzas")).toEqual([{ hotspot: "finanzas", click: true }]);
    expect(matchPresenterGuide("abre cámara")).toEqual([{ hotspot: "camara", click: true }]);
    expect(matchPresenterGuide("abre historial")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-history", click: true },
    ]);
    expect(matchPresenterGuide("abre imágenes")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-media", click: true },
    ]);
    expect(matchPresenterGuide("abre papelera")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-trash", click: true },
    ]);
    expect(matchPresenterGuide("abre whatsapp")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-whatsapp", click: true },
    ]);
    expect(matchPresenterGuide("abre redes")).toEqual([
      { hotspot: "sistema", click: true, force: "open" },
      { hotspot: "nav-networks", click: true },
    ]);
    expect(matchPresenterGuide("abre mapa")).toEqual([{ hotspot: "mapa", click: true }]);
    expect(matchPresenterGuide("abre admin")).toEqual([{ hotspot: "admin", click: true }]);
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
