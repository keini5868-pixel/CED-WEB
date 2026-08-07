"use client";

import { FileText, X } from "lucide-react";

type PdfAttachmentBarProps = {
  filename: string;
  onRemove: () => void;
};

export function PdfAttachmentBar({ filename, onRemove }: PdfAttachmentBarProps) {
  return (
    <div className="mb-2 flex items-center gap-2 rounded-lg border border-cyan-700/40 bg-cyan-950/30 px-3 py-2 text-sm text-cyan-100">
      <FileText className="h-4 w-4 shrink-0 text-cyan-400" aria-hidden />
      <span className="min-w-0 flex-1 truncate" title={filename}>
        {filename}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="shrink-0 rounded p-1 text-cyan-400 hover:bg-cyan-500/10 hover:text-cyan-200"
        aria-label="Quitar documento"
        title="Quitar documento"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
