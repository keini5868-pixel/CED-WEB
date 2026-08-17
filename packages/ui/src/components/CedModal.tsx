"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

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
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] overflow-y-auto overscroll-y-contain [-webkit-overflow-scrolling:touch]"
      style={{ WebkitOverflowScrolling: "touch" }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ced-modal-title"
    >
      <button
        type="button"
        className="fixed inset-0 -z-10 bg-black/75 backdrop-blur-sm"
        aria-label="Cerrar"
        onClick={onClose}
      />
      <div className="flex min-h-[100dvh] flex-col justify-end sm:min-h-0 sm:justify-center sm:p-4">
        <div
          className="relative w-full max-w-lg rounded-t-2xl border border-cyan-400/50 bg-[var(--ced-bg-panel)] ced-glow sm:mx-auto sm:rounded"
          onClick={(e) => e.stopPropagation()}
        >
          <header className="border-b border-cyan-500/25 px-5 py-4 sm:px-6">
            <h2
              id="ced-modal-title"
              className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.2em] text-cyan-300 uppercase"
            >
              {title}
            </h2>
          </header>
          <div className="px-5 py-4 text-sm text-[var(--ced-text)] sm:px-6">{children}</div>
          <footer className="sticky bottom-0 z-10 flex flex-col-reverse gap-2 border-t border-cyan-500/25 bg-[var(--ced-bg-panel)] px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(0,0,0,0.45)] sm:flex-row sm:flex-wrap sm:justify-end sm:gap-3 sm:px-6">
            {footer ?? (
              <CedButton variant="secondary" onClick={onClose}>
                CERRAR
              </CedButton>
            )}
          </footer>
        </div>
      </div>
    </div>,
    document.body,
  );
}
