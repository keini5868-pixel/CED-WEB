/**
 * Verifica conexión Gemini Live native audio (sin languageCode).
 * Uso: node scripts/verify-live-connect.mjs
 */
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const envPath = resolve(root, "apps/api/.env");

function loadApiKey() {
  const raw = readFileSync(envPath, "utf8");
  const match = raw.match(/^GOOGLE_API_KEY=(.+)$/m);
  if (!match) throw new Error("GOOGLE_API_KEY no encontrada en apps/api/.env");
  return match[1].trim().replace(/^["']|["']$/g, "");
}

const MODEL = "gemini-2.5-flash-native-audio-preview-12-2025";

async function main() {
  const apiKey = loadApiKey();
  const { GoogleGenAI, Modality } = await import("@google/genai");

  const ai = new GoogleGenAI({
    apiKey,
    httpOptions: { apiVersion: "v1alpha" },
  });

  let setupOk = false;
  let closed = null;

  const session = await ai.live.connect({
    model: MODEL,
    config: {
      responseModalities: [Modality.AUDIO],
      speechConfig: {
        voiceConfig: { prebuiltVoiceConfig: { voiceName: "Aoede" } },
      },
      inputAudioTranscription: {},
      outputAudioTranscription: {},
    },
    callbacks: {
      onopen: () => console.log("[OK] WebSocket open"),
      onmessage: (msg) => {
        if (msg.setupComplete) {
          setupOk = true;
          console.log("[OK] setupComplete");
        }
      },
      onerror: (e) => console.error("[ERR]", e.message ?? e),
      onclose: (e) => {
        closed = { code: e?.code, reason: e?.reason };
        console.log("[CLOSE]", closed);
      },
    },
  });

  await new Promise((r) => setTimeout(r, 3000));
  try {
    session.close();
  } catch {
    /* ignore */
  }
  await new Promise((r) => setTimeout(r, 500));

  if (closed?.code === 1007) {
    console.error("FALLO: language/config", closed.reason);
    process.exit(1);
  }
  if (!setupOk) {
    console.error("FALLO: sin setupComplete");
    process.exit(1);
  }
  console.log("PASS: Live connect estable");
}

main().catch((err) => {
  console.error("FALLO:", err.message ?? err);
  process.exit(1);
});
