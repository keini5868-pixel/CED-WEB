/** Compromiso CED Shield — solo hash. Nunca transcript ni bytes. */

import { COMPACT_CIRCUIT, COMPACT_CONTRACT, type ShieldKind } from "./circuit";

export type ShieldCommitment = {
  schema: "ced-shield-v1";
  circuit: typeof COMPACT_CIRCUIT;
  contract: typeof COMPACT_CONTRACT;
  kind: ShieldKind;
  content_sha256: string;
  sealed_at: string;
  wallet: string;
  never_on_chain: readonly string[];
};

export const NEVER_ON_CHAIN = [
  "audio",
  "transcript",
  "pdf_bytes",
  "prompts",
] as const;

export function buildShieldCommitment(input: {
  contentSha256: string;
  kind: ShieldKind;
  sealedAt: string;
  wallet: string;
}): ShieldCommitment {
  const hex = input.contentSha256.replace(/^0x/i, "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(hex)) {
    throw new Error("content_sha256 debe ser SHA-256 (64 hex).");
  }
  return {
    schema: "ced-shield-v1",
    circuit: COMPACT_CIRCUIT,
    contract: COMPACT_CONTRACT,
    kind: input.kind,
    content_sha256: hex,
    sealed_at: input.sealedAt,
    wallet: input.wallet,
    never_on_chain: NEVER_ON_CHAIN,
  };
}

/** Canonical string signed by Lace. Order is fixed so judges can re-hash. */
export function commitmentMessage(c: ShieldCommitment): string {
  return [
    c.schema,
    `circuit:${c.circuit}`,
    `contract:${c.contract}`,
    `kind:${c.kind}`,
    `content_sha256:${c.content_sha256}`,
    `sealed_at:${c.sealed_at}`,
    `wallet:${c.wallet}`,
    `never:${c.never_on_chain.join(",")}`,
  ].join("|");
}

export function utf8ToHex(text: string): string {
  return Array.from(new TextEncoder().encode(text))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function utcNowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}
