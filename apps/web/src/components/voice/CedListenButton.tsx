"use client";

import { Mic } from "lucide-react";
import { motion } from "framer-motion";

type CedListenButtonProps = {
  active: boolean;
  busy: boolean;
  paused?: boolean;
  onActivate: () => void;
};

/** Botón compacto de voz — esquina, no panel. */
export function CedListenButton({
  active,
  busy,
  paused = false,
  onActivate,
}: CedListenButtonProps) {
  const label = busy
    ? "…"
    : active
      ? paused
        ? "PAUSA"
        : "EN VIVO"
      : "ESCUCHAR";

  return (
    <motion.button
      type="button"
      onClick={onActivate}
      disabled={busy}
      whileTap={{ scale: busy ? 1 : 0.97 }}
      aria-label={busy ? "Conectando asistente de voz" : active ? "Detener voz" : "Escuchar"}
      className={[
        "flex w-[5.25rem] flex-col items-center gap-1 rounded-xl border px-2 py-2 transition",
        busy
          ? "cursor-wait border-sky-200 bg-sky-50 text-sky-500"
          : active
            ? "border-sky-400 bg-sky-50 text-sky-800 shadow-[0_0_14px_rgba(59,183,255,0.35)]"
            : "border-sky-300 bg-white text-sky-800 shadow-[0_0_10px_rgba(59,183,255,0.18)] hover:border-sky-400 hover:bg-sky-50",
      ].join(" ")}
    >
      <span
        className={[
          "flex h-9 w-9 items-center justify-center rounded-full border",
          active && !paused
            ? "border-sky-300 bg-sky-400/20 shadow-[0_0_12px_rgba(59,183,255,0.45)]"
            : "border-sky-300 bg-sky-100",
        ].join(" ")}
      >
        <Mic className={`h-4 w-4 ${busy ? "animate-pulse text-sky-400" : "text-sky-600"}`} />
      </span>
      <span className="font-[family-name:var(--font-orbitron)] text-[8px] font-bold tracking-[0.14em]">
        {label}
      </span>
    </motion.button>
  );
}
