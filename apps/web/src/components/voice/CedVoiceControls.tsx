"use client";

import {
  Camera,
  FolderOpen,
  History,
  MessageCircle,
  Mic,
  MicOff,
  Pause,
  Settings,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";
import { motion } from "framer-motion";

interface CedVoiceControlsProps {
  micOn: boolean;
  micBusy?: boolean;
  cameraOn: boolean;
  muted: boolean;
  paused: boolean;
  onMic: () => void;
  onCamera: () => void;
  onMute: () => void;
  onPause: () => void;
  onStop: () => void;
  onHistory: () => void;
  onChat: () => void;
  onSettings: () => void;
  onFiles: () => void;
  /** Oculta el botón MIC cuando el lanzador ASISTENTE está activo. */
  hideMicLaunch?: boolean;
}

function ControlBtn({
  active,
  disabled,
  tone = "default",
  label,
  onClick,
  children,
}: {
  active?: boolean;
  disabled?: boolean;
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
      whileTap={{ scale: disabled ? 1 : 0.94 }}
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={[
        "flex h-11 w-11 flex-col items-center justify-center rounded border text-[9px] font-bold tracking-wider transition sm:h-12 sm:w-12",
        disabled
          ? "cursor-not-allowed border-cyan-900/50 bg-black/60 text-cyan-800 opacity-70"
          : active
            ? activeClass
            : "border-cyan-900/80 bg-black/80 text-[#888888] hover:border-cyan-700 hover:text-cyan-400",
      ].join(" ")}
    >
      {children}
    </motion.button>
  );
}

export function CedVoiceControls(props: CedVoiceControlsProps) {
  const showMic = props.micOn || !props.hideMicLaunch;

  return (
    <div className="mt-4 flex w-full max-w-lg flex-wrap items-center justify-center gap-2 px-1 sm:gap-3">
      {showMic ? (
      <ControlBtn
        active={props.micOn}
        disabled={props.micBusy}
        label={props.micBusy ? "Conectando…" : props.micOn ? "Detener asistente" : "Micrófono"}
        onClick={props.onMic}
      >
        {props.micOn ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
        <span className="mt-0.5 hidden sm:inline">{props.micOn ? "LIVE" : "MIC"}</span>
      </ControlBtn>
      ) : null}
      <ControlBtn
        active={props.cameraOn}
        label="Cámara"
        onClick={props.onCamera}
      >
        <Camera className="h-5 w-5" />
        <span className="mt-0.5 hidden sm:inline">CAM</span>
      </ControlBtn>
      <ControlBtn label="Chat de texto" onClick={props.onChat}>
        <MessageCircle className="h-5 w-5" />
        <span className="mt-0.5 hidden sm:inline">CHAT</span>
      </ControlBtn>
      <ControlBtn
        active={props.muted}
        tone={props.muted ? "danger" : "default"}
        label={props.muted ? "Sonido apagado — clic para escuchar" : "Silenciar voz de CED"}
        onClick={props.onMute}
      >
        {props.muted ? (
          <VolumeX className="h-5 w-5 text-red-400" />
        ) : (
          <Volume2 className="h-5 w-5" />
        )}
        <span className="mt-0.5 hidden sm:inline">
          {props.muted ? "MUTED" : "MUTE"}
        </span>
      </ControlBtn>
      <ControlBtn active={props.paused} label="Pausa" onClick={props.onPause}>
        <Pause className="h-5 w-5" />
        <span className="mt-0.5 hidden sm:inline">PAUSA</span>
      </ControlBtn>
      <ControlBtn label="Detener" onClick={props.onStop}>
        <Square className="h-5 w-5 fill-current" />
        <span className="mt-0.5 hidden sm:inline">STOP</span>
      </ControlBtn>
      <ControlBtn label="Historial" onClick={props.onHistory}>
        <History className="h-5 w-5" />
        <span className="mt-0.5 hidden sm:inline">HIST</span>
      </ControlBtn>
      <ControlBtn label="Configuración" onClick={props.onSettings}>
        <Settings className="h-5 w-5" />
        <span className="mt-0.5 hidden sm:inline">CFG</span>
      </ControlBtn>
      <ControlBtn label="Archivos" onClick={props.onFiles}>
        <FolderOpen className="h-5 w-5" />
        <span className="mt-0.5 hidden sm:inline">FILES</span>
      </ControlBtn>
    </div>
  );
}
