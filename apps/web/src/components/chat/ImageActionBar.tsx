"use client";

import { X } from "lucide-react";

export type ImageActionMode =
  | "analyze"
  | "variation"
  | "inspired"
  | "edit"
  | "publish";

type ImageActionBarProps = {
  preview: string;
  mode: ImageActionMode;
  onModeChange: (mode: ImageActionMode) => void;
  onRemove: () => void;
};

const MODES: { id: ImageActionMode; label: string; emoji: string }[] = [
  { id: "publish", label: "Usar para publicar", emoji: "📤" },
  { id: "analyze", label: "Analizar", emoji: "🔍" },
  { id: "variation", label: "Variación", emoji: "🔄" },
  { id: "inspired", label: "Inspirar", emoji: "✨" },
  { id: "edit", label: "Editar", emoji: "✏️" },
];

export function ImageActionBar({
  preview,
  mode,
  onModeChange,
  onRemove,
}: ImageActionBarProps) {
  return (
    <div className="image-action-bar mb-2 flex max-w-full flex-col gap-2 overflow-visible rounded-xl bg-cyan-950/30 p-2 pt-3">
      <div className="attached-image-preview relative inline-block self-start">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={preview}
          alt="Adjuntada"
          className="max-h-24 max-w-[150px] rounded-lg object-cover sm:max-h-[100px] sm:max-w-[200px]"
        />
        <button
          type="button"
          onClick={onRemove}
          className="remove-image-btn absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-black/70 text-white"
          aria-label="Quitar imagen"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="image-actions flex flex-wrap gap-1.5 overflow-visible">
        {MODES.map(({ id, label, emoji }) => (
          <button
            key={id}
            type="button"
            onClick={() => onModeChange(id)}
            className={`action-tag rounded-2xl border px-3 py-1.5 text-[13px] transition-all sm:text-[13px] ${
              mode === id
                ? id === "publish"
                  ? "border-emerald-400 bg-emerald-600 text-white"
                  : "border-cyan-400 bg-cyan-500 text-white"
                : id === "publish"
                  ? "border-emerald-800/50 bg-black/40 text-emerald-300/90 hover:bg-emerald-950/40"
                  : "border-cyan-800/50 bg-black/40 text-cyan-400/80 hover:bg-cyan-950/50"
            }`}
          >
            {emoji} {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function imageActionPlaceholder(mode: ImageActionMode): string {
  switch (mode) {
    case "publish":
      return "Texto del post (opcional) o envíe para usar esta imagen…";
    case "variation":
      return "Describe la variación que quieres…";
    case "inspired":
      return "Describe qué quieres con este estilo…";
    case "edit":
      return "Qué quieres cambiar en la imagen…";
    default:
      return "Pregunta algo sobre la imagen…";
  }
}

export function imageActionHint(mode: ImageActionMode): string {
  switch (mode) {
    case "publish":
      return "📤 Usar para publicar — conecta esta imagen al borrador de Facebook/Instagram";
    case "variation":
      return "🔄 Modo variación — ej: \"versión más moderna y minimalista\"";
    case "inspired":
      return "✨ Modo inspirar — ej: \"algo con este estilo para mi marca\"";
    case "edit":
      return "✏️ Modo editar — ej: \"cambia el fondo a azul oscuro\"";
    default:
      return "🔍 Modo analizar — pregunta sobre la imagen";
  }
}
