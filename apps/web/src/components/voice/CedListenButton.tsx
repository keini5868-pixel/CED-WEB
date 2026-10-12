"use client";

import { Bot, Mic } from "lucide-react";
import { motion } from "framer-motion";

import { isDictationAssistLocked } from "@/lib/chat/dictation-transcript";

type CedListenButtonProps = {
  active: boolean;
  busy: boolean;
  paused?: boolean;
  onActivate: () => void;
};

type CedPresenterButtonProps = {
  active: boolean;
  onActivate: () => void;
};

const dockClass = (active: boolean, busy = false) =>
  [
    "flex w-[2.65rem] flex-col items-center gap-0.5 rounded-lg border px-0.5 py-1 transition lg:w-[3.55rem] lg:px-1",
    busy
      ? "cursor-wait border-[var(--ced-cyan)]/40 bg-[var(--ced-cyan)]/10 text-[var(--ced-cyan)]"
      : active
        ? "border-[var(--ced-cyan)] bg-[var(--ced-cyan)]/15 text-[var(--ced-cyan)] shadow-[0_0_10px_var(--ced-cyan-glow)]"
        : "border-[var(--ced-cyan)]/70 bg-[var(--ced-control-bg)] text-[var(--ced-cyan)] shadow-[0_0_8px_var(--ced-cyan-glow)] hover:bg-[var(--ced-cyan)]/10",
  ].join(" ");

const iconWrapClass = (active: boolean) =>
  [
    "flex h-6 w-6 items-center justify-center rounded-full border lg:h-7 lg:w-7",
    active
      ? "border-[var(--ced-cyan)] bg-[var(--ced-cyan)]/20 shadow-[0_0_8px_var(--ced-cyan-glow)]"
      : "border-[var(--ced-cyan)]/70 bg-[var(--ced-cyan)]/10",
  ].join(" ");

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
      : "ASIST.";

  return (
    <motion.button
      type="button"
      data-ced-listen
      data-ced-hotspot="asistente"
      onClick={(e) => {
        e.stopPropagation();
        if (isDictationAssistLocked()) return;
        onActivate();
      }}
      disabled={busy && !active}
      whileTap={{ scale: busy && !active ? 1 : 0.97 }}
      aria-label={
        busy && !active
          ? "Conectando asistente de voz"
          : active
            ? "Detener voz"
            : "Activar asistente"
      }
      className={dockClass(active && !paused, busy)}
    >
      <span className={iconWrapClass(active && !paused)}>
        <Mic className={`h-3.5 w-3.5 ${busy ? "animate-pulse text-[var(--ced-cyan)]" : "text-[var(--ced-cyan)]"}`} />
      </span>
      <span className="font-[family-name:var(--font-orbitron)] text-[7px] font-bold tracking-[0.1em] lg:text-[8px]">
        {label}
      </span>
    </motion.button>
  );
}

type CedCueButtonProps = {
  active: boolean;
  onActivate: () => void;
};

/** Modo grabación: CED espera «Ok CED» y se calla con «Ok CED, stop». */
export function CedCueButton({ active, onActivate }: CedCueButtonProps) {
  return (
    <motion.button
      type="button"
      data-ced-hotspot="grabar"
      onClick={onActivate}
      whileTap={{ scale: 0.97 }}
      aria-pressed={active}
      aria-label={active ? "Salir del modo grabación" : "Modo grabación"}
      className={`w-full rounded-lg border px-2 py-1.5 font-[family-name:var(--font-orbitron)] text-[9px] font-bold tracking-[0.14em] lg:text-[11px] ${
        active
          ? "border-amber-300 bg-amber-400/20 text-amber-100 shadow-[0_0_10px_rgba(252,211,77,0.35)]"
          : "border-[var(--ced-cyan)]/70 bg-[var(--ced-control-bg)] text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10"
      }`}
    >
      {active ? "GRABAR ON" : "GRABAR"}
    </motion.button>
  );
}

/** Presentador holográfico — al lado del asistente. */
export function CedPresenterButton({ active, onActivate }: CedPresenterButtonProps) {
  return (
    <motion.button
      type="button"
      data-ced-hotspot="robot"
      onClick={onActivate}
      whileTap={{ scale: 0.97 }}
      aria-pressed={active}
      aria-label={active ? "Ocultar robot" : "Mostrar robot"}
      className={dockClass(active)}
    >
      <span className={iconWrapClass(active)}>
        <Bot className="h-3.5 w-3.5 text-[var(--ced-cyan)]" />
      </span>
      <span className="font-[family-name:var(--font-orbitron)] text-[7px] font-bold tracking-[0.1em] lg:text-[8px]">
        ROBOT
      </span>
    </motion.button>
  );
}
