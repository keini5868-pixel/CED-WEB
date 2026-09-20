/** Args del circuit Compact `recordSeal` — espejo de CedShield.compact. */

export const KIND_PDF = 0;
export const KIND_SESSION = 1;

export const COMPACT_CONTRACT = "CedShield.compact";
export const COMPACT_CIRCUIT = "recordSeal";
export const LACE_NETWORK = "preprod";

export type ShieldKind = "pdf" | "session";

export type CompactRecordSealCall = {
  contract: typeof COMPACT_CONTRACT;
  circuit: typeof COMPACT_CIRCUIT;
  language: "compact 0.16";
  network: typeof LACE_NETWORK;
  args: {
    contentHash: string;
    kind: number;
    kindLabel: "PDF" | "SESSION";
  };
  neverOnChain: readonly string[];
};

export function toBytes32Hex(sha256Hex: string): string {
  const hex = sha256Hex.replace(/^0x/i, "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(hex)) {
    throw new Error("contentHash debe ser SHA-256 (32 bytes).");
  }
  return `0x${hex}`;
}

export function buildRecordSealCall(
  sha256Hex: string,
  kind: ShieldKind,
): CompactRecordSealCall {
  return {
    contract: COMPACT_CONTRACT,
    circuit: COMPACT_CIRCUIT,
    language: "compact 0.16",
    network: LACE_NETWORK,
    args: {
      contentHash: toBytes32Hex(sha256Hex),
      kind: kind === "pdf" ? KIND_PDF : KIND_SESSION,
      kindLabel: kind === "pdf" ? "PDF" : "SESSION",
    },
    neverOnChain: ["audio", "transcript", "pdf_bytes", "prompts"],
  };
}
