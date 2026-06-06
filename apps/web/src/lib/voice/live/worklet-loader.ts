/** Carga worklets inline vía Blob URL (patrón Google live-api-web-console). */

export function createWorkletFromSrc(
  workletName: string,
  workletClassSrc: string,
): string {
  const script = new Blob(
    [`registerProcessor("${workletName}", ${workletClassSrc})`],
    { type: "application/javascript" },
  );
  return URL.createObjectURL(script);
}
