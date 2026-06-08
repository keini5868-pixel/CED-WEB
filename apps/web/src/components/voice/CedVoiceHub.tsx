"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { CedTextChatPanel } from "@/components/chat/CedTextChatPanel";

import { CedOrbOverlay } from "@/components/orb/CedOrbOverlay";
import { useHudFeed } from "@/contexts/HudFeedContext";
import { useCedVoiceSession } from "@/hooks/useCedVoiceSession";
import { prefetchEphemeralToken } from "@/lib/voice/ephemeralTokenCache";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import { CedVoiceDebugPanel } from "@/components/voice/CedVoiceDebugPanel";
import { CedVoiceHeardBadge } from "@/components/voice/CedVoiceHeardBadge";
import { CedVoiceControls } from "@/components/voice/CedVoiceControls";
import {
  CedHistoryPanel,
  CedSettingsModal,
  CedStopConfirmModal,
} from "@/components/voice/CedVoiceModals";

const JarvisOrbScene = dynamic(
  () => import("@/components/orb/JarvisOrbScene"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[280px] w-[280px] items-center justify-center rounded-full border border-cyan-500/30 bg-black">
        <span className="font-[family-name:var(--font-orbitron)] text-xs text-cyan-600">
          CARGANDO ORBE…
        </span>
      </div>
    ),
  },
);

/** Centro del dashboard — orbe JARVIS + controles + Gemini Live. */
export function CedVoiceHub() {
  const [chatOpen, setChatOpen] = useState(false);
  const { balance, loaded, refresh: refreshUsage } = useUsageBalance();
  const { pushLine } = useHudFeed();

  useEffect(() => {
    prefetchEphemeralToken();
  }, []);

  const voice = useCedVoiceSession(refreshUsage, {
    onTranscript: (text, role) => {
      pushLine(text, role === "user" ? "voice" : "report");
    },
  });
  const { errorMessage, clearError } = voice;

  useEffect(() => {
    if (!loaded || !errorMessage) return;
    const limitMsg = errorMessage.includes("límite diario");
    const subMsg =
      errorMessage.includes("suscripción") ||
      errorMessage.includes("prueba");
    if (limitMsg && !balance.blocked && !balance.accessDenied) {
      clearError();
    }
    if (subMsg && !balance.accessDenied && balance.plan > 0) {
      clearError();
    }
  }, [
    loaded,
    balance.blocked,
    balance.accessDenied,
    balance.plan,
    errorMessage,
    clearError,
  ]);

  return (
    <div className="flex w-full flex-col items-center px-2 py-4">
      <div className="relative h-[min(52vw,280px)] w-[min(52vw,280px)] max-h-[320px] max-w-[320px] md:h-[300px] md:w-[300px]">
        <JarvisOrbScene
          orbState={voice.orbState}
          audioLevel={voice.audioLevel}
          palette={voice.prefs.palette}
        />
        <CedOrbOverlay
          orbState={voice.orbState}
          audioLevel={voice.audioLevel}
          palette={voice.prefs.palette}
        />
        {voice.cameraOn && voice.cameraPreview ? (
          <img
            src={voice.cameraPreview}
            alt="Vista cámara"
            className="absolute -right-2 -top-2 h-16 w-20 rounded border border-cyan-400/60 object-cover ced-panel-glow sm:h-20 sm:w-24"
          />
        ) : null}
      </div>

      <AnimatePresence mode="wait">
        <motion.p
          key={voice.statusLabel}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="mt-4 text-center font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-widest text-[#00e5ff]"
        >
          {voice.statusLabel}
        </motion.p>
      </AnimatePresence>

      {voice.errorMessage ? (
        <p className="ced-hud-text-secondary mt-2 max-w-sm text-center">
          {voice.errorMessage}
        </p>
      ) : null}

      <CedVoiceHeardBadge
        indicator={voice.heardIndicator}
        micOn={voice.micOn}
        paused={voice.paused}
      />

      {voice.micOn && !voice.paused ? (
        <div className="mt-3 flex h-8 items-end gap-1">
          {Array.from({ length: 12 }).map((_, i) => (
            <motion.div
              key={i}
              className="w-1 rounded-full bg-cyan-400"
              animate={{
                height: 8 + voice.inputLevel * 24 * (0.5 + Math.sin(i) * 0.5),
              }}
              transition={{ duration: 0.08 }}
            />
          ))}
        </div>
      ) : null}

      <CedVoiceControls
        micOn={voice.micOn}
        micBusy={voice.micBusy}
        cameraOn={voice.cameraOn}
        muted={voice.muted}
        paused={voice.paused}
        onMic={() => void voice.toggleMic()}
        onCamera={() => void voice.toggleCamera()}
        onMute={() => voice.setMuted((m) => !m)}
        onPause={voice.togglePause}
        onStop={() => voice.setStopConfirmOpen(true)}
        onHistory={() => voice.setHistoryOpen(true)}
        onChat={() => setChatOpen(true)}
        onSettings={() => voice.setSettingsOpen(true)}
        onFiles={() => {
          /* Fase 5 — upload */
        }}
      />

      <CedStopConfirmModal
        open={voice.stopConfirmOpen}
        onClose={() => voice.setStopConfirmOpen(false)}
        onConfirm={() => {
          voice.stopSession();
          voice.setStopConfirmOpen(false);
        }}
      />
      <CedSettingsModal
        open={voice.settingsOpen}
        onClose={() => voice.setSettingsOpen(false)}
        prefs={voice.prefs}
        onSave={voice.updatePrefs}
        micOn={voice.micOn}
        onApplyVoice={voice.applyVoiceChange}
      />
      <CedHistoryPanel
        open={voice.historyOpen}
        onClose={() => voice.setHistoryOpen(false)}
      />

      <CedTextChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />

      <CedVoiceDebugPanel />
    </div>
  );
}
