import { describe, expect, it } from "vitest";
import {
  cedReceptionGreetingPhrase,
  cedShortReceptionGreeting,
} from "./ced-brief-messages";

describe("cedReceptionGreetingPhrase", () => {
  it("fitline usa saludo corto en español", () => {
    const phrase = cedReceptionGreetingPhrase("fitline", {
      honorific: "Señor",
      gender: "male",
    });
    expect(phrase).toBe(cedShortReceptionGreeting("Señor"));
    expect(phrase.length).toBeLessThan(80);
    expect(phrase.toLowerCase()).not.toMatch(/mercader|importar|hi there|leroy|operativo|protocolos/);
  });

  it("fitline respeta Señora", () => {
    expect(
      cedReceptionGreetingPhrase("fitline", {
        honorific: "Señora",
        gender: "female",
      }),
    ).toBe("Hola, señora. ¿Cómo está? ¿En qué la puedo ayudar?");
  });

  it("sin género usa saludo tú", () => {
    expect(cedShortReceptionGreeting("")).toBe(
      "Hola, ¿cómo estás? ¿En qué te puedo ayudar?",
    );
  });
});
