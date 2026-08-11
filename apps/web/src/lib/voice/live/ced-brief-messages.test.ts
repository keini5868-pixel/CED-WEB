import { describe, expect, it } from "vitest";
import {
  cedReceptionGreetingPhrase,
  cedStandardReceptionGreeting,
} from "./ced-brief-messages";

describe("cedReceptionGreetingPhrase", () => {
  it("fitline usa saludo estándar CED, no temático", () => {
    const phrase = cedReceptionGreetingPhrase("fitline", {
      honorific: "Señor",
      gender: "male",
    });
    expect(phrase).toBe("Sí, Señor, ¿en qué lo puedo ayudar el día de hoy?");
    expect(phrase.toLowerCase()).not.toMatch(/mercader|importar|producto/);
  });

  it("fitline respeta Señora", () => {
    expect(
      cedReceptionGreetingPhrase("fitline", {
        honorific: "Señora",
        gender: "female",
      }),
    ).toBe("Sí, Señora, ¿en qué lo puedo ayudar el día de hoy?");
  });

  it("ignora greetingPhraseJarvis temático en fitline", () => {
    const phrase = cedReceptionGreetingPhrase("fitline", {
      honorific: "Señor",
      greetingPhraseJarvis: "¿Qué producto de mercadería necesitas importar?",
    });
    expect(phrase).toBe(cedStandardReceptionGreeting("Señor"));
  });
});
