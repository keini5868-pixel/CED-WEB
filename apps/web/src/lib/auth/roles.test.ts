import { describe, expect, it } from "vitest";

import { isPresenterOwnerEmail } from "./roles";

describe("isPresenterOwnerEmail", () => {
  const allow = ["keini5868@gmail.com"];

  it("solo el email de la allowlist", () => {
    expect(isPresenterOwnerEmail("keini5868@gmail.com", allow)).toBe(true);
    expect(isPresenterOwnerEmail("  KEINI5868@gmail.com ", allow)).toBe(true);
  });

  it("cualquier otra cuenta queda fuera", () => {
    expect(isPresenterOwnerEmail("cliente@example.com", allow)).toBe(false);
    expect(isPresenterOwnerEmail(null, allow)).toBe(false);
    expect(isPresenterOwnerEmail("", allow)).toBe(false);
  });
});
