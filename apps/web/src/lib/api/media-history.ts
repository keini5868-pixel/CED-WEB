import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";

export type GeneratedImageRow = {
  id: string;
  prompt: string;
  quality: string;
  model: string;
  url: string;
  created_at: string;
};

export async function listGeneratedImages(): Promise<GeneratedImageRow[]> {
  const res = await fetch(cedApiPath("images/history"), {
    credentials: "same-origin",
  });
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Sesión expirada. Cierra sesión y vuelve a entrar.");
    }
    throw new Error("No se pudo cargar el historial de imágenes.");
  }
  const data = await parseApiJson<{ images?: GeneratedImageRow[] }>(res);
  return (data.images ?? []).map((row) => ({
    ...row,
    url: normalizeCedMediaUrl(row.url),
  }));
}

export async function downloadImageBlob(
  url: string,
  filename = "imagen-ced.png",
): Promise<void> {
  const src = normalizeCedMediaUrl(url);
  const res = await fetch(src, { credentials: "same-origin" });
  if (!res.ok) {
    throw new Error("No se pudo descargar la imagen.");
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename.replace(/[^\w\s.-]/g, "") || "imagen-ced.png";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
