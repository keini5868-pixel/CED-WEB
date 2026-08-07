"use client";

import { FileText } from "lucide-react";
import { useRef } from "react";

type PdfUploadButtonProps = {
  onPdfSelected: (file: File) => void;
  disabled?: boolean;
};

const MAX_BYTES = 10 * 1024 * 1024;

function isDocumentFile(file: File): boolean {
  const type = (file.type || "").toLowerCase();
  const name = file.name.toLowerCase();
  if (type === "application/pdf" || name.endsWith(".pdf")) return true;
  if (
    type ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    name.endsWith(".docx")
  ) {
    return true;
  }
  return false;
}

export function PdfUploadButton({ onPdfSelected, disabled }: PdfUploadButtonProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!isDocumentFile(file)) {
      alert("Solo archivos PDF o Word (.docx)");
      return;
    }

    if (file.size > MAX_BYTES) {
      alert("Documento demasiado grande. Máximo 10MB.");
      return;
    }

    onPdfSelected(file);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"
        onChange={handleFileSelect}
        className="hidden"
        aria-hidden
      />
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled}
        className="box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border border-cyan-800/50 bg-black/40 text-cyan-300 hover:bg-cyan-500/10 active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px]"
        aria-label="Adjuntar PDF o Word"
        title="Adjuntar PDF o Word (.docx)"
      >
        <FileText className="h-[18px] w-[18px] shrink-0" />
      </button>
    </>
  );
}
