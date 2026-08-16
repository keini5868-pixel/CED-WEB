"use client";

import { Trash2 } from "lucide-react";

export function SelectToolbar({
  selecting,
  selectedCount,
  onToggle,
  onTrash,
  busy,
}: {
  selecting: boolean;
  selectedCount: number;
  onToggle: () => void;
  onTrash: () => void;
  busy?: boolean;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={onToggle}
        className="rounded border border-cyan-800/60 px-2.5 py-1 text-[10px] uppercase tracking-wider text-cyan-300 hover:bg-cyan-500/10"
      >
        {selecting ? "Cancelar selección" : "Seleccionar archivos"}
      </button>
      {selecting ? (
        <button
          type="button"
          disabled={selectedCount === 0 || busy}
          onClick={onTrash}
          className="rounded border border-rose-500/40 px-2.5 py-1 text-[10px] uppercase tracking-wider text-rose-200 hover:bg-rose-500/10 disabled:opacity-40"
        >
          Papelera ({selectedCount})
        </button>
      ) : null}
    </div>
  );
}

export function TrashIconButton({
  onClick,
  disabled,
  label = "Enviar a papelera",
}: {
  onClick: () => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="rounded p-1 text-cyan-600 hover:bg-rose-500/15 hover:text-rose-300 disabled:opacity-40"
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  );
}
