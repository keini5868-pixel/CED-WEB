"use client";

import { FileText, ImagePlus, Paperclip } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ImageUploadButton } from "@/components/chat/ImageUploadButton";
import { PdfUploadButton } from "@/components/chat/PdfUploadButton";

type AttachMenuButtonProps = {
  onImageSelected: (file: File, preview: string) => void;
  onPdfSelected: (file: File) => void;
  disabled?: boolean;
  /** Solo la grapa (Foto / PDF). Usar en la franja de iconos. */
  clipOnly?: boolean;
};

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const IMAGE_MAX = 5 * 1024 * 1024;
const DOC_MAX = 10 * 1024 * 1024;

function isDocumentFile(file: File): boolean {
  const type = (file.type || "").toLowerCase();
  const name = file.name.toLowerCase();
  if (type === "application/pdf" || name.endsWith(".pdf")) return true;
  return (
    type ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    name.endsWith(".docx")
  );
}

const triggerClass =
  "box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border border-[var(--studio-border)] bg-[var(--studio-composer-bg)] text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10 active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px]";

type MenuCoords = {
  left: number;
  bottom: number;
};

/** En móvil: un clip con menú Foto / Archivo. En escritorio: los dos botones sueltos. */
export function AttachMenuButton({
  onImageSelected,
  onPdfSelected,
  disabled,
  clipOnly = false,
}: AttachMenuButtonProps) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;

    const update = () => {
      const btn = rootRef.current?.querySelector("button");
      if (!btn) return;
      const r = btn.getBoundingClientRect();
      const menuW = 220;
      const gap = 8;
      const left = Math.max(
        gap,
        Math.min(r.right - menuW, window.innerWidth - menuW - gap),
      );
      const bottom = Math.max(gap, window.innerHeight - r.top + gap);
      setCoords({ left, bottom });
    };

    update();
    const onDoc = (ev: MouseEvent | TouchEvent) => {
      const node = ev.target as Node;
      if (rootRef.current?.contains(node)) return;
      const menu = document.getElementById("ced-attach-menu");
      if (menu?.contains(node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("touchstart", onDoc);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  const pickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    setOpen(false);
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) {
      alert("Solo imágenes JPG, PNG, WebP o GIF");
      return;
    }
    if (file.size > IMAGE_MAX) {
      alert("Imagen demasiado grande. Máximo 5MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      onImageSelected(file, event.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const pickPdf = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    setOpen(false);
    if (!file) return;
    if (!isDocumentFile(file)) {
      alert("Solo archivos PDF o Word (.docx)");
      return;
    }
    if (file.size > DOC_MAX) {
      alert("Documento demasiado grande. Máximo 10MB.");
      return;
    }
    onPdfSelected(file);
  };

  const menu =
    open && coords
      ? createPortal(
          <div
            id="ced-attach-menu"
            role="menu"
            style={{
              position: "fixed",
              left: coords.left,
              bottom: coords.bottom,
            }}
            className="z-[400] min-w-[13.5rem] rounded-xl border border-[var(--ced-cyan)]/40 bg-[#071018] py-1 shadow-[0_16px_48px_rgba(0,0,0,0.75)]"
          >
            <button
              type="button"
              role="menuitem"
              disabled={disabled}
              onClick={() => imageInputRef.current?.click()}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm text-[var(--studio-chat-fg)] hover:bg-[var(--ced-cyan)]/10 disabled:opacity-40"
            >
              <ImagePlus className="h-4 w-4 text-[var(--ced-cyan)]" />
              Foto
            </button>
            <button
              type="button"
              role="menuitem"
              disabled={disabled}
              onClick={() => pdfInputRef.current?.click()}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm text-[var(--studio-chat-fg)] hover:bg-[var(--ced-cyan)]/10 disabled:opacity-40"
            >
              <FileText className="h-4 w-4 text-[var(--ced-cyan)]" />
              Archivo PDF o Word
            </button>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <div className={clipOnly ? "hidden" : "hidden lg:contents"}>
        <PdfUploadButton onPdfSelected={onPdfSelected} disabled={disabled} />
        <ImageUploadButton onImageSelected={onImageSelected} disabled={disabled} />
      </div>

      <div ref={rootRef} className={clipOnly ? "relative" : "relative lg:hidden"}>
        <input
          ref={imageInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          onChange={pickImage}
          className="hidden"
          aria-hidden
        />
        <input
          ref={pdfInputRef}
          type="file"
          accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"
          onChange={pickPdf}
          className="hidden"
          aria-hidden
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((v) => !v)}
          className={
            clipOnly
              ? "box-border flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--studio-border)] bg-[var(--studio-composer-bg)] text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10 active:scale-95 disabled:opacity-40 lg:h-8 lg:w-8"
              : triggerClass
          }
          aria-label="Adjuntar foto o archivo"
          aria-expanded={open}
          title="Adjuntar"
        >
          <Paperclip className={clipOnly ? "h-3.5 w-3.5 shrink-0" : "h-[18px] w-[18px] shrink-0"} />
        </button>
        {menu}
      </div>
    </>
  );
}
