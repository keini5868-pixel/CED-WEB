import { describe, expect, it } from "vitest";

import {
  buildShieldCommitment,
  commitmentMessage,
  utf8ToHex,
} from "./commitment";

describe("shield commitment", () => {
  const hash = "ab".repeat(32);

  it("only carries hash fields", () => {
    const c = buildShieldCommitment({
      contentSha256: hash,
      kind: "session",
      sealedAt: "2026-09-29T16:00:00Z",
      wallet: "addr_test1shield",
    });
    expect(c.content_sha256).toBe(hash);
    expect(c).not.toHaveProperty("transcript");
    expect(c).not.toHaveProperty("pdf_bytes");
    expect(c.never_on_chain).toContain("transcript");
    expect(c.wallet).toBe("addr_test1shield");
  });

  it("signs a deterministic message", () => {
    const c = buildShieldCommitment({
      contentSha256: hash,
      kind: "pdf",
      sealedAt: "2026-09-29T16:00:00Z",
      wallet: "mn_shield_1",
    });
    const msg = commitmentMessage(c);
    expect(msg).toContain("ced-shield-v1");
    expect(msg).toContain(`content_sha256:${hash}`);
    expect(utf8ToHex(msg)).toMatch(/^[0-9a-f]+$/);
    expect(utf8ToHex(msg).length).toBe(msg.length * 2);
  });

  it("rejects a non-sha256 digest", () => {
    expect(() =>
      buildShieldCommitment({
        contentSha256: "nope",
        kind: "session",
        sealedAt: "2026-09-29T16:00:00Z",
        wallet: "addr1",
      }),
    ).toThrow(/SHA-256/);
  });
});
