"use client";

import { useEffect, useMemo, useState } from "react";

import { CED_LIFE_ACTION_EVENT, type LifeActionDetail } from "@/lib/lifeActions";
import { CedTextChatPanel } from "@/components/chat/CedTextChatPanel";
import { AdvancedChatPanel } from "@/components/chat/AdvancedChatPanel";
import { FinanceChatPanel } from "@/components/chat/FinanceChatPanel";
import { ModuleShell } from "@/components/modules/ModuleShell";
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
import { CedListenButton } from "@/components/voice/CedListenButton";
import { CedStudioSidebar } from "@/components/hud/CedStudioSidebar";
import { HudUsageBar } from "@/components/hud/HudUsageBar";
import { CED_OPEN_SETTINGS_EVENT } from "@/lib/hud/chrome-events";

/** Dashboard — chat principal + voz compacta. */
export function CedVoiceHub() {
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
      const mod = (detail?.module || "").trim();
      if (mod === "finance") {
        setFinanceOpen(true);
        setAdvancedOpen(false);
      }
      if (mod === "opportunities") {
        setAdvancedOpen(false);
        setFinanceOpen(false);
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
      setChatSeedImage(null);
    },
  }, voiceRoute);

  useEffect(() => {
    if (!voice.micOn) return;
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
  const readyLabel = voice.micOn
    ? voice.statusLabel
    : "Asistente CED listo";

  const listenDock = (
    <div className="flex flex-col items-center gap-3">
      {cameraLive || imageLive ? (
        <div className="relative h-36 w-full max-w-[220px] overflow-hidden rounded-xl">
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
      ) : null}
      <CedListenButton
        active={voice.micOn}
        busy={voice.micBusy}
        paused={voice.paused}
        onActivate={handleMic}
      />
      <CedVoiceHeardBadge
        indicator={voice.heardIndicator}
        micOn={voice.micOn}
        paused={voice.paused}
      />
      {voice.errorMessage ? (
        <p className="max-w-[14rem] text-center text-[11px] text-sky-800/80">
          {voice.errorMessage}
        </p>
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
    </div>
  );

  return (
    <div className="ced-studio flex min-h-0 w-full flex-1 flex-col overflow-hidden pb-16 lg:flex-row lg:pb-0">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-white">
        <div className="ced-studio-status flex shrink-0 items-center gap-2 border-b border-sky-100 px-4 py-2 text-sm">
          <span
            className={`h-2 w-2 rounded-full ${voice.micOn && !voice.paused ? "animate-pulse bg-sky-400" : "bg-sky-500"}`}
            aria-hidden
          />
          <span className="font-medium">{readyLabel}</span>
        </div>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <CedTextChatPanel
            open
            variant="embedded"
            onClose={() => undefined}
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
        </div>
      </section>

      <CedStudioSidebar
        listen={listenDock}
        usage={
          <div className="ced-studio-usage rounded-xl border border-sky-100 bg-white p-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-sky-700">
              uso de datos
            </p>
            <HudUsageBar compact />
          </div>
        }
        extras={
          <div className="flex flex-col gap-0.5">
            <button
              type="button"
              onClick={() => {
                setAdvancedOpen((open) => !open);
                setFinanceOpen(false);
              }}
              className="rounded-lg px-2 py-1.5 text-left text-[13px] text-sky-800/80 hover:bg-sky-100 hover:text-sky-950"
            >
              Avanzado
            </button>
            <button
              type="button"
              onClick={() => {
                setFinanceOpen((open) => !open);
                setAdvancedOpen(false);
              }}
              className="rounded-lg px-2 py-1.5 text-left text-[13px] text-sky-800/80 hover:bg-sky-100 hover:text-sky-950"
            >
              Finanzas
            </button>
            <button
              type="button"
              onClick={() => void voice.toggleCamera()}
              className="rounded-lg px-2 py-1.5 text-left text-[13px] text-sky-800/80 hover:bg-sky-100 hover:text-sky-950"
            >
              {voice.cameraOn ? "Cerrar cámara" : "Cámara"}
            </button>
          </div>
        }
      />

      <div className="lg:hidden">
        <CedActionBar
          micOn={voice.micOn}
          micBusy={voice.micBusy}
          cameraOn={voice.cameraOn}
          chatOpen
          advancedOpen={advancedOpen}
          financeOpen={financeOpen}
          onMic={handleMic}
          onCamera={() => void voice.toggleCamera()}
          onChat={() => undefined}
          onAdvanced={() => {
            setAdvancedOpen((open) => !open);
            setFinanceOpen(false);
          }}
          onFinance={() => {
            setFinanceOpen((open) => !open);
            setAdvancedOpen(false);
          }}
        />
      </div>

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
