"use client";

import { Pause, Square, Volume2, VolumeX } from "lucide-react";
import { motion } from "framer-motion";

import type { HudQuickPopupId } from "@/components/voice/CedHudQuickPopups";

interface CedVoiceControlsProps {
  micOn: boolean;
  muted: boolean;
  paused: boolean;
  onMute: () => void;
  onPause: () => void;
  onStop: () => void;
  quickPopup?: HudQuickPopupId;
  onQuickPopup?: (id: Exclude<HudQuickPopupId, null>) => void;
}

function ControlBtn({
  active,
  tone = "default",
  label,
  onClick,
  children,
}: {
  active?: boolean;
  tone?: "default" | "danger";
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const activeClass =
    tone === "danger"
      ? "border-red-400 bg-red-950/50 text-red-200"
      : "border-cyan-400 bg-cyan-400/20 text-cyan-200 ced-panel-glow";

  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.94 }}
      onClick={onClick}
      title={label}
      aria-label={label}
      className={[
        "flex h-10 w-10 flex-col items-center justify-center rounded border text-[8px] font-bold tracking-wider transition sm:h-11 sm:w-11",
        active
          ? activeClass
          : "border-cyan-900/80 bg-black/80 text-[#888888] hover:border-cyan-700 hover:text-cyan-400",
      ].join(" ")}
    >
      {children}
    </motion.button>
  );
}

/** Controles de sesión en vivo (mute/pausa/stop + atajos). Mic/chat van en la barra inferior. */
export function CedVoiceControls(props: CedVoiceControlsProps) {
  if (!props.micOn) return null;

  return (
    <div className="mt-3 flex items-center justify-center gap-2">
      <ControlBtn
        active={props.muted}
        tone={props.muted ? "danger" : "default"}
        label={props.muted ? "Sonido apagado — clic para escuchar" : "Silenciar voz de CED"}
        onClick={props.onMute}
      >
        {props.muted ? (
          <VolumeX className="h-4 w-4 text-red-400" />
        ) : (
          <Volume2 className="h-4 w-4" />
        )}
      </ControlBtn>
      <ControlBtn active={props.paused} label="Pausa" onClick={props.onPause}>
        <Pause className="h-4 w-4" />
      </ControlBtn>
      <ControlBtn label="Detener" onClick={props.onStop}>
        <Square className="h-4 w-4 fill-current" />
      </ControlBtn>
      <ControlBtn
        active={props.quickPopup === "weather"}
        label="Clima"
        onClick={() => props.onQuickPopup?.("weather")}
      >
        <span className="text-base leading-none">🌤️</span>
      </ControlBtn>
      <ControlBtn
        active={props.quickPopup === "events"}
        label="Eventos"
        onClick={() => props.onQuickPopup?.("events")}
      >
        <span className="text-base leading-none">🔔</span>
      </ControlBtn>
    </div>
  );
}
