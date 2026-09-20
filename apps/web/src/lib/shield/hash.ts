/** SHA-256 en el navegador. El texto nunca se manda a Midnight. */

export async function sha256Hex(data: string | ArrayBuffer): Promise<string> {
  const bytes =
    typeof data === "string" ? new TextEncoder().encode(data) : new Uint8Array(data);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export const DEMO_ARTIFACT = [
  "CED Shield sample artifact",
  "kind: session",
  "never_on_chain: transcript, pdf_bytes, audio, prompts",
  "midnight receives: sha256 only",
].join("\n");
