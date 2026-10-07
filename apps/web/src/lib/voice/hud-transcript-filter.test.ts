import { describe, expect, it } from "vitest";

import { looksLikeImageToolDump, shouldHideHudTranscript } from "./hud-transcript-filter";

const XML_DUMP = `Listo. Voy a generar ese flyer.

Va.

<generate_image>
{
"prompt": "Flyer profesional fondo oscuro",
"size": "1080x1350",
"style": "professional_dark_minimal"
}
</generate_image>`;

describe("hud transcript filter", () => {
  it("hides xml generate_image dumps", () => {
    expect(looksLikeImageToolDump(XML_DUMP)).toBe(true);
    expect(shouldHideHudTranscript(XML_DUMP)).toBe(true);
  });

  it("keeps natural speech", () => {
    expect(shouldHideHudTranscript("Listo. Aquí está tu imagen generada.")).toBe(false);
    expect(looksLikeImageToolDump("Listo. Aquí está tu imagen generada.")).toBe(false);
  });
});
