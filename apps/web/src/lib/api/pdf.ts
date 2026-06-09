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
): Promise<PdfArtifact> {
  const res = await fetch(cedApiPath("pdf/generate"), {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      content,
      conversation_id: conversationId ?? undefined,
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

export async function downloadPdfBlob(
  fileId: string,
  filename = "documento-ced.pdf",
): Promise<void> {
  const res = await fetch(pdfDownloadUrl(fileId), { credentials: "same-origin" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const blob = await res.blob();
  if (blob.size < 100) {
    throw new Error("PDF vacío");
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
