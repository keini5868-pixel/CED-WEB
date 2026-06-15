"use client";

import { ImagePlus } from "lucide-react";
import { useRef } from "react";

type ImageUploadButtonProps = {
  onImageSelected: (file: File, preview: string) => void;
  disabled?: boolean;
};

const VALID_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const MAX_BYTES = 5 * 1024 * 1024;

export function ImageUploadButton({ onImageSelected, disabled }: ImageUploadButtonProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!VALID_TYPES.includes(file.type)) {
      alert("Solo imágenes JPG, PNG, WebP o GIF");
      return;
    }

    if (file.size > MAX_BYTES) {
      alert("Imagen demasiado grande. Máximo 5MB.");
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const preview = event.target?.result as string;
      onImageSelected(file, preview);
    };
    reader.readAsDataURL(file);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        onChange={handleFileSelect}
        className="hidden"
        aria-hidden
      />
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled}
        className="box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border border-cyan-800/50 bg-black/40 text-cyan-300 hover:bg-cyan-500/10 active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px]"
        aria-label="Adjuntar imagen"
        title="Adjuntar imagen"
      >
        <ImagePlus className="h-[18px] w-[18px] shrink-0" />
      </button>
    </>
  );
}
