import { normalizeCedMediaUrl } from "@/lib/api/media-url";

function sanitizeFilename(name: string): string {
  const base = name
    .trim()
    .slice(0, 48)
    .replace(/[^\w\s.-]/g, "")
    .replace(/\s+/g, "-")
    .toLowerCase();
  return base || "ced-imagen";
}

function extensionFromMime(mime: string): string {
  if (mime.includes("jpeg") || mime.includes("jpg")) return "jpg";
  if (mime.includes("webp")) return "webp";
  if (mime.includes("gif")) return "gif";
  return "png";
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

/** Descarga imagen generada (proxy CED, data URL o http). */
export async function downloadGeneratedImage(
  url: string,
  prompt?: string,
): Promise<void> {
  const src = normalizeCedMediaUrl(url.trim());
  if (!src) {
    throw new Error("URL de imagen inválida.");
  }

  const label = sanitizeFilename(prompt || "ced-imagen");

  if (src.startsWith("data:")) {
    const res = await fetch(src);
    const blob = await res.blob();
    const ext = extensionFromMime(blob.type || "image/png");
    triggerBlobDownload(blob, `${label}.${ext}`);
    return;
  }

  const res = await fetch(src, { credentials: "same-origin" });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data.detail;
    } catch {
      /* respuesta no JSON */
    }
    throw new Error(detail || `No se pudo descargar la imagen (error ${res.status}).`);
  }

  const blob = await res.blob();
  if (blob.size < 100) {
    throw new Error("La imagen está vacía o corrupta.");
  }
  const ext = extensionFromMime(blob.type || res.headers.get("content-type") || "image/png");
  triggerBlobDownload(blob, `${label}.${ext}`);
}
