import { describe, expect, it } from "vitest";
import {
  cedReceptionGreetingPhrase,
  cedStandardReceptionGreeting,
} from "./ced-brief-messages";

describe("cedReceptionGreetingPhrase", () => {
  it("fitline usa saludo estilo Retell Jarvis en español", () => {
    const phrase = cedReceptionGreetingPhrase("fitline", {
      honorific: "Señor",
      gender: "male",
    });
    expect(phrase.toLowerCase()).toMatch(/señor|ced|servicio|ayudarle|comenzamos|necesita/);
    expect(phrase.toLowerCase()).not.toMatch(/mercader|importar|hi there|what's on your mind/);
    expect(phrase).not.toMatch(/Claro,\s*claro/i);
  });

  it("fitline respeta Señora", () => {
    const phrase = cedReceptionGreetingPhrase("fitline", {
      honorific: "Señora",
      gender: "female",
    });
    expect(phrase).toMatch(/Señora/);
    expect(phrase).not.toMatch(/\bSeñor\b/);
  });

  it("ignora greetingPhraseJarvis temático o en inglés en fitline", () => {
    const phrase = cedReceptionGreetingPhrase("fitline", {
      honorific: "Señor",
      greetingPhraseJarvis: "Hi there! What's on your mind today?",
    });
    expect(phrase.toLowerCase()).not.toMatch(/hi there|what's on your mind/);
    expect(phrase).toMatch(/Señor|CED|servicio|ayudarle/i);
  });

  it("cedStandardReceptionGreeting es español formal", () => {
    expect(cedStandardReceptionGreeting("Señor")).toMatch(/A su servicio/);
  });
});
