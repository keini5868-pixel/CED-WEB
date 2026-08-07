import { describe, expect, it } from "vitest";

import { coerceDisplayText, formatApiDetail } from "./display-text";

describe("coerceDisplayText", () => {
  it("keeps plain strings", () => {
    expect(coerceDisplayText("hola")).toBe("hola");
  });

  it("never returns [object Object] for plain objects", () => {
    const out = coerceDisplayText({ text: "contenido real largo" });
    expect(out).toBe("contenido real largo");
    expect(out).not.toContain("[object Object]");
  });

  it("extracts FastAPI validation detail arrays", () => {
    const out = coerceDisplayText([
      {
        type: "value_error",
        loc: ["body", "content"],
        msg: "Tu texto es demasiado largo (máximo 50000 caracteres). Súbelo como archivo PDF o Word (.docx) con el botón de documento.",
      },
    ]);
    expect(out).toContain("demasiado largo");
    expect(out).not.toContain("[object Object]");
  });

  it("joins content-part arrays", () => {
    expect(
      coerceDisplayText([
        { type: "text", text: "parte A" },
        { type: "text", text: "parte B" },
      ]),
    ).toBe("parte A\nparte B");
  });

  it("formatApiDetail uses fallback when empty", () => {
    expect(formatApiDetail(null, "fallo")).toBe("fallo");
  });
});
