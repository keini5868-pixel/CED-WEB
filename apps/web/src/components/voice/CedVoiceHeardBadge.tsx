"use client";

import { motion } from "framer-motion";

import type { VoiceHeardIndicator } from "@/hooks/useCedVoiceSession";

const STATUS_COPY: Record<
  VoiceHeardIndicator["status"],
  { title: string; hint?: string }
> = {
  hidden: { title: "" },
  listening: {
    title: "Esperando tu voz…",
    hint: "Habla claro. Si CED habla mucho, interrúmpelo hablando encima.",
  },
  heard: {
    title: "CED te escuchó",
    hint: "Procesando tu mensaje…",
  },
  responding: {
    title: "CED te escuchó",
    hint: "CED está respondiendo…",
  },
  no_voice_reply: {
    title: "CED te escuchó",
    hint: "Sin respuesta de voz en este turno. Revisa volumen o auriculares.",
  },
};

type Props = {
  indicator: VoiceHeardIndicator;
  micOn: boolean;
  paused: boolean;
};

/** Badge fijo: confirma que Gemini transcribió al usuario, con o sin audio de respuesta. */
export function CedVoiceHeardBadge({ indicator, micOn, paused }: Props) {
  if (!micOn || paused || indicator.status === "hidden") {
    return null;
  }

  const copy = STATUS_COPY[indicator.status];
  const showCheck =
    indicator.status === "heard" ||
    indicator.status === "responding" ||
    indicator.status === "no_voice_reply";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="ced-voice-heard-badge mt-3 w-full max-w-md px-1"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="ced-voice-heard-badge__inner flex flex-col gap-2 rounded-lg border px-4 py-3">
        <div className="flex items-center gap-2">
          <span
            className={`ced-voice-heard-badge__dot h-2.5 w-2.5 shrink-0 rounded-full ${
              indicator.status === "listening"
                ? "ced-voice-heard-badge__dot--pulse"
                : showCheck
                  ? "ced-voice-heard-badge__dot--ok"
                  : ""
            }`}
            aria-hidden
          />
          <span className="font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-[#00e5ff]">
            {copy.title}
          </span>
          {showCheck ? (
            <span
              className="ml-auto text-[10px] font-bold uppercase tracking-widest text-emerald-400/90"
              aria-hidden
            >
              OK
            </span>
          ) : null}
        </div>

        {copy.hint ? (
          <p className="ced-hud-text-muted text-xs leading-snug">{copy.hint}</p>
        ) : null}

        {indicator.userText ? (
          <p className="ced-hud-text-secondary border-t border-cyan-900/40 pt-2 text-sm leading-snug">
            <span className="ced-hud-text-muted text-[10px] uppercase tracking-wide">
              Dijiste:{" "}
            </span>
            {indicator.userText}
          </p>
        ) : null}
      </div>
    </motion.div>
  );
}
