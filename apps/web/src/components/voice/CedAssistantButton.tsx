"use client";

import { Sparkles } from "lucide-react";
import { motion } from "framer-motion";

interface CedAssistantButtonProps {
  active: boolean;
  busy: boolean;
  paused?: boolean;
  onActivate: () => void;
}

/** Un solo tap: permiso de mic + conexión + saludo de CED. */
export function CedAssistantButton({
  active,
  busy,
  paused = false,
  onActivate,
}: CedAssistantButtonProps) {
  if (active) {
    return (
      <div
        className="mt-5 flex w-full max-w-xs flex-col items-center gap-2 rounded-xl border-2 border-emerald-400/60 bg-emerald-950/30 px-6 py-4"
        role="status"
        aria-live="polite"
      >
        <span className="flex items-center gap-2 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-[0.2em] text-emerald-300">
          <span className="relative flex h-2.5 w-2.5">
            {!paused ? (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            ) : null}
            <span
              className={`relative inline-flex h-2.5 w-2.5 rounded-full ${paused ? "bg-amber-400" : "bg-emerald-400"}`}
            />
          </span>
          {paused ? "ASISTENTE EN PAUSA" : "MICRÓFONO ACTIVO"}
        </span>
        <span className="text-center text-[9px] font-normal tracking-[0.12em] text-emerald-400/80">
          {paused ? "Reanuda con PAUSA para escuchar" : "CED está escuchando · habla cuando quieras"}
        </span>
      </div>
    );
  }

  return (
    <motion.button
      type="button"
      onClick={onActivate}
      disabled={busy}
      whileTap={{ scale: busy ? 1 : 0.97 }}
      className={[
        "group relative mt-5 w-full max-w-xs overflow-hidden rounded-xl border-2 px-6 py-4",
        "font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-[0.22em]",
        "transition-all duration-300",
        busy
          ? "cursor-wait border-cyan-500/40 bg-cyan-950/40 text-cyan-400/80"
          : "border-cyan-300/70 bg-gradient-to-br from-cyan-400/20 via-cyan-500/10 to-violet-500/15 text-cyan-100 ced-glow hover:border-cyan-200 hover:from-cyan-400/30 hover:to-violet-400/20",
      ].join(" ")}
      aria-label={busy ? "Conectando asistente" : "Activar asistente CED"}
    >
      <span
        className="pointer-events-none absolute inset-0 opacity-0 transition group-hover:opacity-100"
        aria-hidden
        style={{
          background:
            "radial-gradient(circle at 50% 0%, rgba(0,229,255,0.25), transparent 65%)",
        }}
      />
      <span className="relative flex flex-col items-center gap-2">
        <span className="flex items-center gap-2">
          <Sparkles
            className={`h-4 w-4 ${busy ? "animate-pulse text-cyan-400" : "text-cyan-300"}`}
          />
          {busy ? "CONECTANDO…" : "ASISTENTE CED"}
          <Sparkles
            className={`h-4 w-4 ${busy ? "animate-pulse text-cyan-400" : "text-cyan-300"}`}
          />
        </span>
        {!busy ? (
          <span className="text-[9px] font-normal tracking-[0.14em] text-cyan-400/75">
            TOCA UNA VEZ · VOZ INMEDIATA
          </span>
        ) : (
          <span className="text-[9px] font-normal tracking-wider text-cyan-500/70">
            Permiso mic · CED Voice
          </span>
        )}
      </span>
    </motion.button>
  );
}
