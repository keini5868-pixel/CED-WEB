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
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4"
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
      <div className="relative flex max-h-[min(92dvh,100dvh)] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-cyan-400/50 bg-[var(--ced-bg-panel)] ced-glow sm:max-h-[min(88dvh,720px)] sm:rounded">
        <header className="shrink-0 border-b border-cyan-500/25 px-5 py-4 sm:px-6">
          <h2
            id="ced-modal-title"
            className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.2em] text-cyan-300 uppercase"
          >
            {title}
          </h2>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-5 py-4 text-sm text-cyan-100/90 [-webkit-overflow-scrolling:touch] sm:px-6">
          {children}
        </div>
        <footer className="shrink-0 flex flex-wrap justify-end gap-3 border-t border-cyan-500/25 bg-[var(--ced-bg-panel)] px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6">
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
