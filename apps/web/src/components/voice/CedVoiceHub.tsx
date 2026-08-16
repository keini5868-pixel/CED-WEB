"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { CED_LIFE_ACTION_EVENT, type LifeActionDetail } from "@/lib/lifeActions";
import { CedTextChatPanel } from "@/components/chat/CedTextChatPanel";
import { AdvancedChatPanel } from "@/components/chat/AdvancedChatPanel";
import { FinanceChatPanel } from "@/components/chat/FinanceChatPanel";
import { ModuleShell } from "@/components/modules/ModuleShell";
import { CedOrbOverlay } from "@/components/orb/CedOrbOverlay";
import { useHudFeed } from "@/contexts/HudFeedContext";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";
import { useCedVoiceSession } from "@/hooks/useCedVoiceSession";
import { prefetchEphemeralToken } from "@/lib/voice/ephemeralTokenCache";
import { unlockVoiceAudioOnGesture } from "@/lib/voice/live/audio-context";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import {
  cierrePreviewVoiceRoute,
  getPreviewPersona,
  isCierrePartnerPreview,
} from "@/lib/preview/cierrePartnerPreview";
import {
  VoiceLimitModal,
  voiceLimitReasonFromBalance,
} from "@/components/billing/VoiceLimitModal";
import { CedVoiceDebugPanel } from "@/components/voice/CedVoiceDebugPanel";
import { CedVoiceImagePreview } from "@/components/voice/CedVoiceImagePreview";
import { CedVoiceHeardBadge } from "@/components/voice/CedVoiceHeardBadge";
import { CedAssistantButton } from "@/components/voice/CedAssistantButton";
import { CedVoiceControls } from "@/components/voice/CedVoiceControls";
import { CedActionBar } from "@/components/voice/CedActionBar";
import { CedCameraPreview } from "@/components/voice/CedCameraPreview";
import {
  CedHudQuickPopups,
  type HudQuickPopupId,
} from "@/components/voice/CedHudQuickPopups";
import {
  CedHistoryPanel,
  CedSettingsModal,
  CedStopConfirmModal,
} from "@/components/voice/CedVoiceModals";
import { CED_OPEN_SETTINGS_EVENT } from "@/lib/hud/chrome-events";

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
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [financeOpen, setFinanceOpen] = useState(false);
  const [voiceLimitOpen, setVoiceLimitOpen] = useState(false);
  const [chatSeedImage, setChatSeedImage] = useState<{
    url: string;
    prompt?: string;
  } | null>(null);
  const [chatSeedPrompt, setChatSeedPrompt] = useState<string | null>(null);
  const [quickPopup, setQuickPopup] = useState<HudQuickPopupId>(null);
  const [voiceImagePreview, setVoiceImagePreview] = useState<{
    url: string;
    prompt?: string;
  } | null>(null);
  const { balance, loaded, refresh: refreshUsage } = useUsageBalance();
  const { pushVoiceLine, pushVoiceImage, updateVoiceImage, clearAgentPartial, setActiveModule } =
    useHudFeed();
  const [previewTick, setPreviewTick] = useState(0);

  useEffect(() => {
    const sync = () => {
      getPreviewPersona();
      setPreviewTick((n) => n + 1);
    };
    sync();
    window.addEventListener("ced-preview-persona", sync);
    return () => window.removeEventListener("ced-preview-persona", sync);
  }, []);

  useEffect(() => {
    const onOpen = (ev: Event) => {
      const detail = (ev as CustomEvent<{ module?: string }>).detail;
      if ((detail?.module || "").trim() === "finance") {
        setFinanceOpen(true);
      }
    };
    window.addEventListener("ced-open-module", onOpen);
    return () => window.removeEventListener("ced-open-module", onOpen);
  }, []);

  const voiceRoute = useMemo(() => {
    void previewTick;
    if (isCierrePartnerPreview()) {
      return cierrePreviewVoiceRoute();
    }
    return {
      planId: balance.planId,
      voiceStack: balance.voiceStack,
      voiceTransport: balance.voiceTransport,
    };
  }, [
    previewTick,
    balance.planId,
    balance.voiceStack,
    balance.voiceTransport,
  ]);

  useEffect(() => {
    const onModuleActive = (ev: Event) => {
      const detail = (ev as CustomEvent<{ module?: string | null }>).detail;
      const mod = detail?.module;
      if (!mod) {
        setActiveModule(null);
        return;
      }
      const allowed = [
        "map",
        "camera",
        "publish",
        "image_gen",
        "pdf",
        "web_search",
        "prospection",
        "memory",
      ] as const;
      if ((allowed as readonly string[]).includes(mod)) {
        setActiveModule(mod as (typeof allowed)[number]);
      }
    };
    window.addEventListener("ced-module-active", onModuleActive);
    return () => window.removeEventListener("ced-module-active", onModuleActive);
  }, [setActiveModule]);

  useEffect(() => {
    if (voiceRoute.planId === "cierre" || voiceRoute.voiceStack === "gemini") {
      prefetchEphemeralToken("cedar", { voiceProfile: "fitline" });
    } else {
      prefetchEphemeralToken();
    }
  }, [voiceRoute.planId, voiceRoute.voiceStack]);

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
        const normalized = normalizeCedMediaUrl(imageUrl);
        pushVoiceImage(normalized, { prompt, role: "model", status: "ready" });
        setVoiceImagePreview({ url: normalized, prompt });
        setChatOpen(false);
        setChatSeedImage(null);
      }
    };
    window.addEventListener("ced-voice-tool-result", onToolResult);
    return () => window.removeEventListener("ced-voice-tool-result", onToolResult);
  }, []);

  const voice = useCedVoiceSession(refreshUsage, {
    onTranscript: (text, role, options) => {
      pushVoiceLine(text, role, options);
    },
    onClearAgentPartial: clearAgentPartial,
    onGeneratedImage: (url, prompt) => {
      pushVoiceImage(url, { prompt, role: "model", status: "ready" });
      setVoiceImagePreview({ url, prompt });
      setChatOpen(false);
      setChatSeedImage(null);
    },
  }, voiceRoute);

  useEffect(() => {
    if (!voice.micOn) return;
    setChatOpen(false);
    setChatSeedImage(null);
  }, [voice.micOn]);

  useEffect(() => {
    const onLifeAction = (ev: Event) => {
      const detail = (ev as CustomEvent<LifeActionDetail>).detail;
      const prompt = detail?.prompt?.trim();
      if (detail?.activateVoice === true) {
        unlockVoiceAudioOnGesture();
        voice.primeSessionMediaFromGesture();
        if (!voice.micOn) {
          void voice.toggleMic();
        }
      }
      if (prompt) {
        setChatSeedPrompt(prompt);
      }
      setChatOpen(true);
    };
    window.addEventListener(CED_LIFE_ACTION_EVENT, onLifeAction);
    return () => window.removeEventListener(CED_LIFE_ACTION_EVENT, onLifeAction);
  }, [voice.micOn, voice.primeSessionMediaFromGesture, voice.toggleMic]);

  useEffect(() => {
    const onSettings = () => voice.setSettingsOpen(true);
    window.addEventListener(CED_OPEN_SETTINGS_EVENT, onSettings);
    return () => window.removeEventListener(CED_OPEN_SETTINGS_EVENT, onSettings);
  }, [voice.setSettingsOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("settings") !== "1") return;
    voice.setSettingsOpen(true);
    url.searchParams.delete("settings");
    const qs = url.searchParams.toString();
    window.history.replaceState(
      {},
      "",
      `${url.pathname}${qs ? `?${qs}` : ""}${url.hash}`,
    );
  }, [voice.setSettingsOpen]);

  const activateMic = () => {
    unlockVoiceAudioOnGesture();
    voice.primeSessionMediaFromGesture();
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
  };

  const handleMic = () => {
    if (voice.micOn) {
      void voice.toggleMic();
      return;
    }
    activateMic();
  };

  const { errorMessage, clearError } = voice;

  const voiceLimit =
    loaded && !balance.authFailed
      ? voiceLimitReasonFromBalance(balance)
      : null;

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

  const cameraLive = voice.cameraOn && Boolean(voice.cameraStream);
  const imageLive = Boolean(voiceImagePreview?.url) && !cameraLive;
  const canvasBusy = cameraLive || imageLive;

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center px-3 py-4 pb-24 sm:max-w-lg sm:px-2">
      <div
        className={[
          "relative mx-auto overflow-hidden",
          canvasBusy
            ? "aspect-[4/3] w-full max-w-[min(92vw,520px)] rounded-xl"
            : "h-[min(52vw,280px)] w-[min(52vw,280px)] max-h-[320px] max-w-[320px] md:h-[300px] md:w-[300px]",
        ].join(" ")}
      >
        <div
          className={
            canvasBusy
              ? "absolute bottom-2 left-2 z-10 h-[72px] w-[72px] overflow-hidden rounded-full border border-cyan-500/40 bg-black/70 shadow-[0_0_16px_rgba(0,229,255,0.2)] md:h-[88px] md:w-[88px] [&>div]:!h-full [&>div]:!w-full [&>div]:!max-h-none [&>div]:!max-w-none"
              : "relative h-full w-full"
          }
        >
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
          overlay
          stream={voice.cameraStream}
          active={voice.cameraOn}
          facing={voice.cameraFacing}
          onFlipCamera={() => void voice.flipCamera()}
        />

        <CedVoiceImagePreview
          overlay
          url={imageLive ? voiceImagePreview?.url ?? null : null}
          prompt={voiceImagePreview?.prompt}
          onDismiss={() => setVoiceImagePreview(null)}
        />
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

      {!voice.micOn ? (
        <CedAssistantButton
          active={false}
          busy={voice.micBusy}
          paused={voice.paused}
          onActivate={activateMic}
        />
      ) : null}

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
        muted={voice.muted}
        paused={voice.paused}
        quickPopup={quickPopup}
        onQuickPopup={(id) => setQuickPopup((prev) => (prev === id ? null : id))}
        onMute={() => voice.setMuted((m) => !m)}
        onPause={voice.togglePause}
        onStop={() => voice.setStopConfirmOpen(true)}
      />

      <CedActionBar
        micOn={voice.micOn}
        micBusy={voice.micBusy}
        cameraOn={voice.cameraOn}
        chatOpen={chatOpen}
        advancedOpen={advancedOpen}
        financeOpen={financeOpen}
        onMic={handleMic}
        onCamera={() => void voice.toggleCamera()}
        onChat={() => {
          setChatOpen((open) => !open);
          setAdvancedOpen(false);
          setFinanceOpen(false);
        }}
        onAdvanced={() => {
          setAdvancedOpen((open) => !open);
          setChatOpen(false);
          setFinanceOpen(false);
        }}
        onFinance={() => {
          setFinanceOpen((open) => !open);
          setChatOpen(false);
          setAdvancedOpen(false);
        }}
      />

      <CedHudQuickPopups active={quickPopup} onClose={() => setQuickPopup(null)} />

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

      <AdvancedChatPanel
        open={advancedOpen}
        onClose={() => setAdvancedOpen(false)}
      />

      <FinanceChatPanel
        open={financeOpen}
        onClose={() => setFinanceOpen(false)}
      />

      <ModuleShell />

      <CedTextChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        seedImage={chatSeedImage}
        onSeedConsumed={() => setChatSeedImage(null)}
        seedPrompt={chatSeedPrompt}
        onSeedPromptConsumed={() => setChatSeedPrompt(null)}
        onVoiceImageAttached={
          voice.voiceSessionActive
            ? (preview, file) => {
                const itemId = pushVoiceImage(preview, {
                  fileName: file?.name,
                  fileSize: file?.size,
                  status: "uploading",
                  role: "user",
                });
                void voice.registerChatImageForVoice(preview, file).then((result) => {
                  if (!result?.image_url) return;
                  updateVoiceImage(itemId, {
                    imageUrl: result.image_url,
                    text: "Imagen lista para CED",
                    uploadStatus: "ready",
                    fileName: result.filename || file?.name,
                    fileSize: result.size_bytes ?? file?.size,
                  });
                }).catch(() => {
                  updateVoiceImage(itemId, {
                    text: "Error al subir imagen",
                    uploadStatus: "error",
                  });
                });
              }
            : undefined
        }
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
