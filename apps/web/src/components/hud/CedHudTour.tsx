"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { CedButton } from "@ced/ui";

const TOUR_KEY = "ced-hud-tour-v1";

export function CedHudTour() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      if (!sessionStorage.getItem(TOUR_KEY) && !localStorage.getItem(TOUR_KEY)) {
        setOpen(true);
      }
    } catch {
      setOpen(true);
    }
  }, []);

  if (!mounted || !open) return null;

  function dismiss() {
    try {
      localStorage.setItem(TOUR_KEY, "1");
    } catch {
      /* ignore */
    }
    setOpen(false);
  }

  return createPortal(
    <div className="fixed inset-0 z-[210] flex items-end justify-center bg-black/45 p-4 sm:items-center">
      <div className="ced-panel-glow w-full max-w-md rounded-lg border border-cyan-500/40 bg-black p-5 shadow-2xl">
        <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-bold text-[var(--ced-cyan)]">
          CED en un minuto
        </h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-[#e0e0e0]">
          <li>
            <span className="text-cyan-200">Habla</span> con el micrófono o
            escribe en el chat.
          </li>
          <li>
            Pide un <span className="text-cyan-200">copy o guion</span> — CED lo
            entrega en el mismo turno.
          </li>
          <li>
            Pide un <span className="text-cyan-200">PDF o una imagen</span> y
            descárgalo desde Chats → PDFs / Imágenes.
          </li>
        </ol>
        <p className="mt-3 text-xs text-[#888888]">
          Jarvis es la voz del asistente. Shield / Midnight es otro módulo
          (privacidad ZK), apagado en producción y no mezclado con la voz.
        </p>
        <CedButton className="mt-4 w-full" onClick={dismiss}>
          Entendido
        </CedButton>
      </div>
    </div>,
    document.body,
  );
}
