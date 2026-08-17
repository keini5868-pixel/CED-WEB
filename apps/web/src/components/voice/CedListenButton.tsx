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
          ? "cursor-wait border-[var(--ced-cyan)]/40 bg-[var(--ced-cyan)]/10 text-[var(--ced-cyan)]"
          : active
            ? "border-[var(--ced-cyan)] bg-[var(--ced-cyan)]/15 text-[var(--ced-cyan)] shadow-[0_0_14px_var(--ced-cyan-glow)]"
            : "border-[var(--ced-cyan)]/70 bg-white text-[var(--ced-cyan)] shadow-[0_0_10px_var(--ced-cyan-glow)] hover:bg-[var(--ced-cyan)]/10",
      ].join(" ")}
    >
      <span
        className={[
          "flex h-9 w-9 items-center justify-center rounded-full border",
          active && !paused
            ? "border-[var(--ced-cyan)] bg-[var(--ced-cyan)]/20 shadow-[0_0_12px_var(--ced-cyan-glow)]"
            : "border-[var(--ced-cyan)]/70 bg-[var(--ced-cyan)]/10",
        ].join(" ")}
      >
        <Mic className={`h-4 w-4 ${busy ? "animate-pulse text-[var(--ced-cyan)]" : "text-[var(--ced-cyan)]"}`} />
      </span>
      <span className="font-[family-name:var(--font-orbitron)] text-[8px] font-bold tracking-[0.14em]">
        {label}
      </span>
    </motion.button>
  );
}
