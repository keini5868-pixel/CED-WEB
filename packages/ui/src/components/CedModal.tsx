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

function lockPageScroll() {
  const scrollY = window.scrollY;
  document.body.dataset.cedModalScroll = String(scrollY);
  document.body.style.position = "fixed";
  document.body.style.top = `-${scrollY}px`;
  document.body.style.left = "0";
  document.body.style.right = "0";
  document.body.style.width = "100%";
}

function unlockPageScroll() {
  const scrollY = Number(document.body.dataset.cedModalScroll || "0");
  document.body.style.position = "";
  document.body.style.top = "";
  document.body.style.left = "";
  document.body.style.right = "";
  document.body.style.width = "";
  delete document.body.dataset.cedModalScroll;
  window.scrollTo(0, scrollY);
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
    lockPageScroll();
    return () => {
      document.removeEventListener("keydown", onKey);
      unlockPageScroll();
    };
  }, [open, onClose]);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-end justify-center sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ced-modal-title"
    >
      <div
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        aria-hidden
        onClick={onClose}
      />
      <div
        className="relative grid h-[min(92dvh,100dvh)] w-full max-w-lg grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-t-2xl border border-cyan-400/50 bg-[var(--ced-bg-panel)] ced-glow sm:h-auto sm:max-h-[min(88dvh,720px)] sm:rounded"
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
        <div
          className="overflow-y-scroll overscroll-y-contain px-5 py-4 text-sm text-cyan-100/90 [touch-action:pan-y] [-webkit-overflow-scrolling:touch] sm:px-6"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          {children}
        </div>
        <footer className="flex flex-col-reverse gap-2 border-t border-cyan-500/25 bg-[var(--ced-bg-panel)] px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(0,0,0,0.45)] sm:flex-row sm:flex-wrap sm:justify-end sm:gap-3 sm:px-6">
          {footer ?? (
            <CedButton variant="secondary" onClick={onClose}>
              CERRAR
            </CedButton>
          )}
        </footer>
      </div>
    </div>,
    document.body,
  );
}
