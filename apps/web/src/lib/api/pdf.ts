import { cedApiPath } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type PdfArtifact = {
  file_id: string;
  filename: string;
  title: string;
  conversation_id?: string;
  created_at?: string;
  download_path?: string;
};

export async function generatePdf(
  title: string,
  content: string,
  conversationId?: string | null,
  userRequest?: string | null,
): Promise<PdfArtifact> {
  const res = await fetch(cedApiPath("pdf/generate"), {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      content,
      conversation_id: conversationId ?? undefined,
      user_request: userRequest?.trim() || content || title,
    }),
  });
  const data = await parseApiJson<PdfArtifact & { ok?: boolean; detail?: string }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo generar el PDF.");
  }
  return {
    file_id: data.file_id!,
    filename: data.filename!,
    title: data.title || title,
    download_path: data.download_path,
  };
}

export async function listSessionPdfs(): Promise<PdfArtifact[]> {
  const res = await fetch(cedApiPath("pdf/list"), { credentials: "same-origin" });
  if (!res.ok) return [];
  const data = await res.json();
  return data.pdfs ?? [];
}

export function pdfDownloadUrl(fileId: string): string {
  return cedApiPath(`pdf/download/${fileId}`);
}

function pdfDownloadError(status: number, detail?: string): string {
  if (status === 401) return "Sesión expirada. Cierra sesión y vuelve a entrar.";
  if (status === 404) return "PDF no encontrado. Genera uno nuevo o revisa Supabase.";
  if (status === 502) return "La API no responde. Revisa Railway (servicio CED-WEB).";
  return detail || `No se pudo descargar (error ${status}).`;
}

/** Descarga PDF autenticado vía proxy same-origin (/api/ced/...). */
export async function downloadPdfBlob(
  fileId: string,
  filename = "documento-ced.pdf",
): Promise<void> {
  const id = fileId.trim();
  if (!/^[a-f0-9]{32}$/i.test(id)) {
    throw new Error("ID de PDF inválido. Pide a CED que genere el documento de nuevo.");
  }
  const url = pdfDownloadUrl(id);
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data.detail;
    } catch {
      /* respuesta no JSON */
    }
    throw new Error(pdfDownloadError(res.status, detail));
  }

  const blob = await res.blob();
  if (blob.size < 100) {
    throw new Error("El PDF está vacío o corrupto.");
  }
  const header = new Uint8Array(await blob.slice(0, 5).arrayBuffer());
  const magic = String.fromCharCode(...header);
  if (!magic.startsWith("%PDF")) {
    throw new Error("El servidor no devolvió un PDF válido.");
  }

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename.replace(/[^\w\s.-]/g, "") || "documento-ced.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
