"use client";

import {
  Camera,
  MessageCircle,
  Mic,
  MicOff,
  Sparkles,
  Wallet,
} from "lucide-react";

type CedActionBarProps = {
  micOn: boolean;
  micBusy?: boolean;
  cameraOn: boolean;
  chatOpen?: boolean;
  advancedOpen?: boolean;
  financeOpen?: boolean;
  onMic: () => void;
  onCamera: () => void;
  onChat: () => void;
  onAdvanced: () => void;
  onFinance: () => void;
};

function ActionBtn({
  label,
  active,
  disabled,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={active}
      className={[
        "flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-lg px-1 py-1.5 transition",
        disabled
          ? "cursor-not-allowed text-cyan-800"
          : active
            ? "bg-cyan-400/15 text-cyan-100"
            : "text-cyan-500 hover:bg-cyan-400/10 hover:text-cyan-200",
      ].join(" ")}
    >
      {children}
      <span className="max-w-full truncate font-[family-name:var(--font-orbitron)] text-[8px] font-semibold uppercase tracking-wider sm:text-[9px]">
        {label}
      </span>
    </button>
  );
}

/** Acceso inmediato a voz, cámara y chats — no sustituye la sesión, solo la dispara. */
export function CedActionBar({
  micOn,
  micBusy,
  cameraOn,
  chatOpen,
  advancedOpen,
  financeOpen,
  onMic,
  onCamera,
  onChat,
  onAdvanced,
  onFinance,
}: CedActionBarProps) {
  return (
    <nav
      aria-label="Acciones CED"
      className="pointer-events-auto fixed inset-x-0 bottom-0 z-40 border-t border-cyan-500/25 bg-[#060b14]/95 px-2 pt-1.5 backdrop-blur-md pb-[max(0.5rem,env(safe-area-inset-bottom))]"
    >
      <div className="mx-auto flex max-w-lg items-stretch gap-0.5 sm:gap-1">
        <ActionBtn
          label="Mic"
          active={micOn}
          disabled={micBusy}
          onClick={onMic}
        >
          {micOn ? (
            <Mic className="h-5 w-5" strokeWidth={1.75} />
          ) : (
            <MicOff className="h-5 w-5" strokeWidth={1.75} />
          )}
        </ActionBtn>
        <ActionBtn label="Cámara" active={cameraOn} onClick={onCamera}>
          <Camera className="h-5 w-5" strokeWidth={1.75} />
        </ActionBtn>
        <ActionBtn label="Chat" active={chatOpen} onClick={onChat}>
          <MessageCircle className="h-5 w-5" strokeWidth={1.75} />
        </ActionBtn>
        <ActionBtn label="Avanzado" active={advancedOpen} onClick={onAdvanced}>
          <Sparkles className="h-5 w-5" strokeWidth={1.75} />
        </ActionBtn>
        <ActionBtn label="Finanzas" active={financeOpen} onClick={onFinance}>
          <Wallet className="h-5 w-5" strokeWidth={1.75} />
        </ActionBtn>
      </div>
    </nav>
  );
}
