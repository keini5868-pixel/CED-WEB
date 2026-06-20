"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { CedTextChatPanel } from "@/components/chat/CedTextChatPanel";

import { CedOrbOverlay } from "@/components/orb/CedOrbOverlay";
import { useHudFeed } from "@/contexts/HudFeedContext";
import { useCedVoiceSession } from "@/hooks/useCedVoiceSession";
import { prefetchEphemeralToken } from "@/lib/voice/ephemeralTokenCache";
import { unlockVoiceAudioOnGesture } from "@/lib/voice/live/audio-context";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import {
  VoiceLimitModal,
  voiceLimitReasonFromBalance,
} from "@/components/billing/VoiceLimitModal";
import { CedVoiceDebugPanel } from "@/components/voice/CedVoiceDebugPanel";
import { CedVoiceImagePreview } from "@/components/voice/CedVoiceImagePreview";
import { CedVoiceHeardBadge } from "@/components/voice/CedVoiceHeardBadge";
import { CedAssistantButton } from "@/components/voice/CedAssistantButton";
import { CedVoiceControls } from "@/components/voice/CedVoiceControls";
import { CedCameraPreview } from "@/components/voice/CedCameraPreview";
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
  const [voiceLimitOpen, setVoiceLimitOpen] = useState(false);
  const [chatSeedImage, setChatSeedImage] = useState<{
    url: string;
    prompt?: string;
  } | null>(null);
  const [voiceImagePreview, setVoiceImagePreview] = useState<{
    url: string;
    prompt?: string;
  } | null>(null);
  const { balance, loaded, refresh: refreshUsage } = useUsageBalance();
  const { pushVoiceLine, pushVoiceImage } = useHudFeed();

  useEffect(() => {
    prefetchEphemeralToken();
  }, []);

  useEffect(() => {
    const onToolResult = (ev: Event) => {
      const detail = (ev as CustomEvent<{ tool_name?: string; result?: Record<string, unknown> }>)
        .detail;
      const toolName = detail?.tool_name ?? "";
      const result = detail?.result;
      const imageUrl =
        typeof result?.image_url === "string"
          ? result.image_url
          : typeof result?.url === "string"
            ? result.url
            : null;
      if (toolName.includes("image") && imageUrl) {
        const prompt =
          typeof result?.prompt === "string" ? result.prompt : undefined;
        setVoiceImagePreview({ url: imageUrl, prompt });
        setChatSeedImage({ url: imageUrl, prompt });
        setChatOpen(true);
      }
    };
    window.addEventListener("ced-voice-tool-result", onToolResult);
    return () => window.removeEventListener("ced-voice-tool-result", onToolResult);
  }, []);

  const voice = useCedVoiceSession(refreshUsage, {
    onTranscript: (text, role, options) => {
      pushVoiceLine(text, role, options);
    },
    onGeneratedImage: (url, prompt) => {
      pushVoiceImage(url, { prompt, role: "model", status: "ready" });
      setVoiceImagePreview({ url, prompt });
      setChatSeedImage({ url, prompt });
      setChatOpen(true);
    },
  });
  const { errorMessage, clearError } = voice;

  const voiceLimit = loaded ? voiceLimitReasonFromBalance(balance) : null;

  useEffect(() => {
    if (!loaded) return;
    if (!voiceLimitReasonFromBalance(balance)) {
      setVoiceLimitOpen(false);
    }
  }, [loaded, balance.blocked, balance.accessDenied, balance.accessMessage, balance.plan]);

  useEffect(() => {
    if (!loaded || !errorMessage) return;
    const limit = voiceLimitReasonFromBalance(balance);
    if (!limit) {
      if (
        errorMessage.includes("límite diario") ||
        errorMessage.includes("límite de voz")
      ) {
        clearError();
      }
      return;
    }
    const limitMsg =
      errorMessage.includes("límite diario") ||
      errorMessage.includes("límite de voz");
    const subMsg =
      errorMessage.includes("suscripción") ||
      errorMessage.includes("prueba") ||
      errorMessage.includes("plan");
    if (limitMsg || subMsg) {
      setVoiceLimitOpen(true);
    }
  }, [
    loaded,
    balance.blocked,
    balance.accessDenied,
    balance.accessMessage,
    balance.plan,
    errorMessage,
    clearError,
  ]);

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center px-3 py-4 sm:max-w-lg sm:px-2">
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
      </div>

      <CedCameraPreview
        stream={voice.cameraStream}
        active={voice.cameraOn}
        facing={voice.cameraFacing}
        onFlipCamera={() => void voice.flipCamera()}
      />

      <CedVoiceImagePreview
        url={voiceImagePreview?.url ?? null}
        prompt={voiceImagePreview?.prompt}
        onOpenChat={() => setChatOpen(true)}
        onDismiss={() => setVoiceImagePreview(null)}
      />

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

      <CedAssistantButton
        active={voice.micOn}
        busy={voice.micBusy}
        paused={voice.paused}
        onActivate={() => {
          unlockVoiceAudioOnGesture();
          void (async () => {
            const fresh = await refreshUsage();
            const snapshot = fresh ?? balance;
            const limit = voiceLimitReasonFromBalance(snapshot);
            if (limit) {
              setVoiceLimitOpen(true);
              return;
            }
            void voice.toggleMic();
          })();
        }}
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
        hideMicLaunch
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

      <CedTextChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        seedImage={chatSeedImage}
        onSeedConsumed={() => setChatSeedImage(null)}
        onVoiceImageAttached={(preview, file) => {
          void voice.registerChatImageForVoice(preview, file);
        }}
        voicePublishActive={voice.voiceSessionActive}
      />

      <VoiceLimitModal
        open={voiceLimitOpen}
        onClose={() => setVoiceLimitOpen(false)}
        reason={voiceLimit ?? "daily_limit"}
        planMinutesDaily={balance.plan}
      />

      <CedVoiceDebugPanel />
    </div>
  );
}
