"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";

import { CedButton } from "./CedButton";

export interface CedModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function CedModal({
  open,
  onClose,
  title,
  children,
  footer,
}: CedModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ced-modal-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        aria-label="Cerrar"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg rounded border border-cyan-400/50 bg-[var(--ced-bg-panel)] p-6 ced-glow">
        <header className="mb-4 border-b border-cyan-500/25 pb-3">
          <h2
            id="ced-modal-title"
            className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.2em] text-cyan-300 uppercase"
          >
            {title}
          </h2>
        </header>
        <div className="text-sm text-cyan-100/90">{children}</div>
        <footer className="mt-6 flex flex-wrap justify-end gap-3">
          {footer ?? (
            <CedButton variant="secondary" onClick={onClose}>
              CERRAR
            </CedButton>
          )}
        </footer>
      </div>
    </div>
  );
}
