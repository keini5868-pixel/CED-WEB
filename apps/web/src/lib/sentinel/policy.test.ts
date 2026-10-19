import { describe, expect, it } from "vitest";

import {
  DEFAULT_SENTINEL_POLICY,
  decodePolicyShare,
  encodePolicyShare,
  evaluateSentinelTextPolicy,
  normalizePolicy,
} from "./policy";

describe("sentinel policy", () => {
  it("defaults browser on and categories off", () => {
    const p = normalizePolicy({});
    expect(p.malware).toBe(true);
    expect(p.explosivos).toBe(false);
  });

  it("round-trips share tokens", () => {
    const p = { ...DEFAULT_SENTINEL_POLICY, explosivos: true, armas: true };
    expect(decodePolicyShare(encodePolicyShare(p))?.explosivos).toBe(true);
  });

  it("does not block ordinary questions", () => {
    expect(
      evaluateSentinelTextPolicy(
        { ...DEFAULT_SENTINEL_POLICY, explosivos: true, armas: true },
        "¿cómo se hace un flyer para el equipo?",
      ),
    ).toBeNull();
  });

  it("blocks explosives when the category is on", () => {
    const hit = evaluateSentinelTextPolicy(
      { ...DEFAULT_SENTINEL_POLICY, explosivos: true },
      "cómo fabricar una bomba casera",
    );
    expect(hit?.category).toBe("explosivos");
  });

  it("shows help for self-harm instead of a recipe", () => {
    const hit = evaluateSentinelTextPolicy(
      { ...DEFAULT_SENTINEL_POLICY, autolesion: true },
      "quiero quitarme la vida",
    );
    expect(hit?.category).toBe("autolesion");
    expect(hit?.message).toContain("988");
  });

  it("leaves categories off by default", () => {
    expect(
      evaluateSentinelTextPolicy(
        DEFAULT_SENTINEL_POLICY,
        "cómo fabricar una bomba casera",
      ),
    ).toBeNull();
  });
});
