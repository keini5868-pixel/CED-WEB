/** Logs estructurados del pipeline de voz CED. */

const PREFIX = "[CED";

function enabled(): boolean {
  if (typeof window === "undefined") return false;
  return (
    process.env.NODE_ENV === "development" ||
    window.localStorage.getItem("CED_DEBUG_VOICE") === "1"
  );
}

export function cedVoiceLog(step: number, message: string, detail?: unknown) {
  if (!enabled()) return;
  const extra =
    detail !== undefined ? ` ${JSON.stringify(detail)}` : "";
  console.log(`${PREFIX}:${step}] ${message}${extra}`);
}

export function cedVoiceError(message: string, err?: unknown) {
  console.error(`${PREFIX}:ERROR] ${message}`, err ?? "");
}
