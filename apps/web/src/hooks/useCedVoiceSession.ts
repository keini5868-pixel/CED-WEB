"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { OrbState, VoiceSessionPreferences } from "@ced/types";
import { ORB_STATE_LABELS } from "@ced/types";

import { appendConversationMessage } from "@/lib/api/conversations";
import { generatePdf } from "@/lib/api/pdf";
import { fetchVoiceBrief } from "@/lib/api/openai";
import { saveMemory, searchMemory } from "@/lib/api/memory";
import { schedulePanelSearch } from "@/lib/api/panels";
import {
  disableProspection,
  enableProspection,
  fetchProspectionReport,
} from "@/lib/api/prospection";
import { publishFacebook, publishInstagram } from "@/lib/api/social";
import { fetchVisionWebSearch } from "@/lib/api/vision";
import {
  endVoiceSession,
  startVoiceSession,
  tickVoiceSession,
} from "@/lib/api/usage";
import { useAudioAnalyser } from "@/hooks/useAudioAnalyser";
import { unlockVoiceAudioOnGesture } from "@/lib/voice/live/audio-context";
import {
  CedLiveClient,
  type CedLiveHandlers,
} from "@/lib/voice/live/ced-live-client";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import { cedVoiceLog } from "@/lib/voice/cedVoiceLogger";
import { isBenignRealtimeError } from "@/lib/voice/realtimeErrors";
import { normalizeVoiceName } from "@/lib/voice/openaiVoices";
import {
  ACTIVAR_PROSPECCION,
  BUSCAR_LO_VISIBLE,
  BUSCAR_MEMORIA,
  CONSULTAR_SISTEMA_AVANZADO,
  DESACTIVAR_PROSPECCION,
  GUARDAR_MEMORIA,
  REPORTE_PROSPECCION,
  PUBLICAR_FACEBOOK,
  PUBLICAR_INSTAGRAM,
  GENERAR_PDF,
} from "@/lib/voice/liveTools";
import { isAdvancedConfirmAnswer, isComplexAnalysisRequest, isExplicitAdvancedRequest, isSearchStatusIntent, isWeatherIntent, isWebResearchIntent, shouldAllowAdvancedTool, webBriefKind, webBriefTimeoutMs } from "@/lib/voice/webResearchIntent";
import {
  isMemoryRecallIntent,
  isRememberIntent,
  isVisualSearchIntent,
  parseRememberContent,
} from "@/lib/voice/visualSearchIntent";
import { voiceTelemetry } from "@/lib/voice/voiceTelemetry";
import {
  loadVoicePreferences,
  saveMicPreference,
  saveVoicePreferences,
} from "@/lib/voice/preferences";

const CAMERA_IDLE_MS = 5 * 60 * 1000;
const VIDEO_SEND_INTERVAL_MS = 1500;
const VIDEO_CAPTURE_WIDTH = 640;
const VIDEO_CAPTURE_HEIGHT = 480;
const USAGE_TICK_SECONDS = 15;
const MAX_WS_RECONNECT = 3;
/** Si el turno no cierra, liberar mic/UI (WebRTC). */
const TURN_STUCK_MS = 16000;
const PROCESSING_STUCK_MS = 10000;

export interface CedVoiceSessionCallbacks {
  onTranscript?: (text: string, role: "user" | "model") => void;
}

export type VoiceHeardStatus =
  | "hidden"
  | "listening"
  | "heard"
  | "responding"
  | "no_voice_reply";

export interface VoiceHeardIndicator {
  status: VoiceHeardStatus;
  userText: string | null;
  heardAt: number | null;
}

const INITIAL_HEARD: VoiceHeardIndicator = {
  status: "hidden",
  userText: null,
  heardAt: null,
};

export function useCedVoiceSession(
  onUsageRefresh?: () => void,
  callbacks?: CedVoiceSessionCallbacks,
) {
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [statusLabel, setStatusLabel] = useState(ORB_STATE_LABELS.idle);
  const [micOn, setMicOn] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [muted, setMuted] = useState(false);
  const [paused, setPaused] = useState(false);
  const [prefs, setPrefs] = useState<VoiceSessionPreferences>(loadVoicePreferences);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [heardIndicator, setHeardIndicator] =
    useState<VoiceHeardIndicator>(INITIAL_HEARD);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [micBusy, setMicBusy] = useState(false);

  const micStreamRef = useRef<MediaStream | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const cameraIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clientRef = useRef<CedLiveClient | null>(null);
  const usageSessionRef = useRef<string | null>(null);
  const conversationRef = useRef<string | null>(null);
  const usageIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastVideoSentRef = useRef(0);
  const mutedRef = useRef(muted);
  const pausedRef = useRef(paused);
  const modelRepliedTurnRef = useRef(false);
  const orbStateRef = useRef<OrbState>(orbState);
  const voiceSessionGenRef = useRef(0);
  const handlersRef = useRef<CedLiveHandlers | null>(null);
  const reconnectAttemptRef = useRef(0);
  const prefsRef = useRef(prefs);
  const modelSpeakingRef = useRef(false);
  const clientWebSearchRef = useRef(false);
  const webFetchRef = useRef(false);
  const lastWebQueryRef = useRef("");
  const lastUserUtteranceRef = useRef("");
  const advancedConfirmPendingRef = useRef(false);
  const advancedConfirmAskedRef = useRef(false);
  const pendingAdvancedPromptRef = useRef("");
  const webSearchDebounceRef = useRef<number | null>(null);
  const cameraPreviewRef = useRef<string | null>(null);
  const cameraCaptureVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraCaptureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const micOnRef = useRef(micOn);

  useEffect(() => {
    prefsRef.current = prefs;
  }, [prefs]);
  useEffect(() => {
    orbStateRef.current = orbState;
  }, [orbState]);
  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);
  useEffect(() => {
    micOnRef.current = micOn;
  }, [micOn]);

  const captureCameraJpeg = useCallback((): string | null => {
    const video = cameraCaptureVideoRef.current;
    if (!video || video.videoWidth === 0) return cameraPreviewRef.current;
    let canvas = cameraCaptureCanvasRef.current;
    if (!canvas) {
      canvas = document.createElement("canvas");
      cameraCaptureCanvasRef.current = canvas;
    }
    canvas.width = VIDEO_CAPTURE_WIDTH;
    canvas.height = VIDEO_CAPTURE_HEIGHT;
    const ctx = canvas.getContext("2d");
    ctx?.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.72);
    cameraPreviewRef.current = dataUrl;
    return dataUrl;
  }, []);

  const inputLevel = useAudioAnalyser(micStream, micOn && !paused);
  const inputLevelRef = useRef(0);
  useEffect(() => {
    inputLevelRef.current = inputLevel;
  }, [inputLevel]);
  const audioLevel =
    orbState === "listening"
      ? inputLevel
      : orbState === "speaking"
        ? 0.4
        : orbState === "processing"
          ? 0.5
          : 0.15;

  const persistMessage = useCallback(
    async (role: "user" | "model", text: string) => {
      const cid = conversationRef.current;
      if (!cid || !text.trim()) return;
      try {
        await appendConversationMessage(cid, role, text);
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const clearUsageInterval = useCallback(() => {
    if (usageIntervalRef.current) {
      clearInterval(usageIntervalRef.current);
      usageIntervalRef.current = null;
    }
  }, []);

  const resetCameraIdleTimer = useCallback(() => {
    if (cameraIdleTimerRef.current) clearTimeout(cameraIdleTimerRef.current);
    if (!cameraOn) return;
    cameraIdleTimerRef.current = setTimeout(() => {
      setCameraOn(false);
      setCameraStream(null);
      cameraPreviewRef.current = null;
      cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
      cameraStreamRef.current = null;
    }, CAMERA_IDLE_MS);
  }, [cameraOn]);

  const stopSession = useCallback(async () => {
    voiceSessionGenRef.current += 1;
    clearUsageInterval();
    clientRef.current?.disconnect();
    clientRef.current = null;
    handlersRef.current = null;

    if (usageSessionRef.current) {
      try {
        await endVoiceSession(usageSessionRef.current);
      } catch {
        /* ignore */
      }
      usageSessionRef.current = null;
    }

    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    setMicStream(null);
    cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
    cameraStreamRef.current = null;
    setMicOn(false);
    setCameraOn(false);
    setCameraStream(null);
    cameraPreviewRef.current = null;
    setHeardIndicator(INITIAL_HEARD);
    modelRepliedTurnRef.current = false;
    modelSpeakingRef.current = false;
    clientWebSearchRef.current = false;
    webFetchRef.current = false;
    lastWebQueryRef.current = "";
    if (webSearchDebounceRef.current) {
      clearTimeout(webSearchDebounceRef.current);
      webSearchDebounceRef.current = null;
    }
    reconnectAttemptRef.current = 0;
    advancedConfirmPendingRef.current = false;
    advancedConfirmAskedRef.current = false;
    pendingAdvancedPromptRef.current = "";
    setPaused(false);
    setOrbState("idle");
    setStatusLabel(ORB_STATE_LABELS.idle);
    saveMicPreference(false);
    onUsageRefresh?.();
  }, [clearUsageInterval, onUsageRefresh]);

  const toggleCameraRef = useRef<(force?: boolean) => Promise<void>>(
    async () => undefined,
  );

  const toggleCamera = useCallback(
    async (force?: boolean) => {
      const next = force ?? !cameraOn;
      if (!next) {
        cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
        cameraStreamRef.current = null;
        setCameraOn(false);
        setCameraStream(null);
        cameraPreviewRef.current = null;
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: "user",
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 24, max: 30 },
          },
        });
        cameraStreamRef.current = stream;
        setCameraStream(stream);
        setCameraOn(true);
        setStatusLabel("Activando cámara…");
        resetCameraIdleTimer();
      } catch {
        setErrorMessage(
          "Por favor permite el acceso a la cámara para que CED pueda ver.",
        );
      }
    },
    [cameraOn, resetCameraIdleTimer],
  );
  toggleCameraRef.current = toggleCamera;

  const toggleMic = useCallback(async () => {
    if (micBusy) return;
    if (micOn) {
      await stopSession();
      return;
    }

    unlockVoiceAudioOnGesture();

    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMessage("Tu navegador no soporta captura de micrófono.");
      setOrbState("error");
      return;
    }
    if (!window.isSecureContext) {
      setErrorMessage(
        "El micrófono requiere HTTPS o localhost. Abre CED desde http://localhost:3000",
      );
      setOrbState("error");
      return;
    }

    setMicBusy(true);
    setErrorMessage(null);
    setOrbState("processing");
    setStatusLabel("Activando micrófono…");

    const sessionGen = voiceSessionGenRef.current + 1;
    voiceSessionGenRef.current = sessionGen;
    const isStale = () => voiceSessionGenRef.current !== sessionGen;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: { ideal: 24000 },
          echoCancellation: { ideal: true },
          noiseSuppression: { ideal: true },
          autoGainControl: { ideal: true },
        },
      });
      micStreamRef.current = stream;
      setMicStream(stream);

      setMicOn(true);
      saveMicPreference(true);

      const voiceSession = await startVoiceSession();
      usageSessionRef.current = voiceSession.session_id;
      conversationRef.current = voiceSession.conversation_id;
      onUsageRefresh?.();

      const client = new CedLiveClient();
      clientRef.current = client;
      client.setRemoteMuted(mutedRef.current);
      client.setMicTrackEnabled(!pausedRef.current);

      usageIntervalRef.current = setInterval(() => {
        const sid = usageSessionRef.current;
        if (!sid) return;
        void (async () => {
          try {
            const data = await tickVoiceSession(sid, USAGE_TICK_SECONDS);
            if (!data) return;
            onUsageRefresh?.();
            if (data.blocked || data.should_disconnect) {
              setErrorMessage(
                "Has alcanzado tu límite diario de voz. Recarga o continúa mañana.",
              );
              await stopSession();
            } else if (data.warning_level === "critical") {
              setStatusLabel("Queda poco tiempo de voz hoy (95%)…");
            } else if (data.warning_level === "warn") {
              setStatusLabel("Has usado el 80% de tu voz diaria…");
            } else if (data.access_denied) {
              setErrorMessage(
                "Tu suscripción no está activa. Renueva en Precios para usar la voz.",
              );
              await stopSession();
            }
          } catch {
            /* ignore */
          }
        })();
      }, USAGE_TICK_SECONDS * 1000);

      const micActiveRef = { current: true };
      const greetingSentRef = { current: false };
      const setupTimerRef = { current: null as number | null };
      const responseWatchdogRef = { current: null as number | null };
      const lastResponseStartRef = { current: 0 };

      const clearResponseWatchdog = () => {
        if (responseWatchdogRef.current) {
          clearTimeout(responseWatchdogRef.current);
          responseWatchdogRef.current = null;
        }
      };

      const releaseStuckConversation = (reason: string) => {
        cedVoiceLog(4, "Watchdog conversación", { reason });
        clearResponseWatchdog();
        modelSpeakingRef.current = false;
        if (!clientWebSearchRef.current) {
          webFetchRef.current = false;
        }
        client.forceReleaseTurn();
        client.setMicTrackEnabled(!pausedRef.current);
        client.flushInputAudioBuffer();
        if (micActiveRef.current && !clientWebSearchRef.current) {
          enableListeningUi();
        }
      };

      const scheduleResponseWatchdog = () => {
        clearResponseWatchdog();
        responseWatchdogRef.current = window.setTimeout(() => {
          responseWatchdogRef.current = null;
          if (isStale() || !micActiveRef.current) return;
          if (
            modelSpeakingRef.current ||
            client.isResponseActive() ||
            orbStateRef.current === "processing" ||
            orbStateRef.current === "speaking"
          ) {
            releaseStuckConversation("turn_timeout");
          }
        }, TURN_STUCK_MS);
      };

      const enableListeningUi = () => {
        if (isStale() || !micActiveRef.current) return;
        setHeardIndicator({ status: "listening", userText: null, heardAt: null });
        if (!webFetchRef.current && !modelSpeakingRef.current && !clientWebSearchRef.current) {
          setOrbState("listening");
          setStatusLabel(ORB_STATE_LABELS.listening);
        }
      };

      const runWebSearch = (query: string) => {
        const q = query.trim();
        if (!q || webFetchRef.current || isStale()) return;
        if (modelSpeakingRef.current) {
          cedVoiceLog(5, "Web search diferido — CED ya está respondiendo");
          return;
        }
        cedVoiceLog(5, "Web search", { q: q.slice(0, 80), kind: webBriefKind(q) });
        webFetchRef.current = true;
        clientWebSearchRef.current = true;
        lastWebQueryRef.current = q;
        setOrbState("processing");
        setStatusLabel("Buscando en internet…");

        const kind = webBriefKind(q);
        schedulePanelSearch(q, kind);

        void (async () => {
          let succeeded = false;
          let narrated = false;

          const narrate = (text: string) => {
            if (isStale() || narrated) return;
            narrated = true;
            client.sendNarrationBrief(text.trim());
          };

          try {
            const result = await fetchVoiceBrief(
              q,
              kind,
              webBriefTimeoutMs(kind),
            );
            if (isStale()) return;
            if (result.ok) {
              succeeded = true;
              cedVoiceLog(6, "Web search ok", {
                len: result.summary.length,
                source: result.source,
              });
              narrate(result.summary);
            } else {
              cedVoiceLog(4, "Web search fail", {
                error: result.error,
                code: result.code,
              });
              const spoken =
                result.code === "missing_tavily"
                  ? "la búsqueda web requiere configurar Tavily en el servidor. Contacte al administrador."
                  : result.code === "client_timeout"
                    ? "la búsqueda tardó demasiado. Inténtelo de nuevo."
                    : result.error?.includes("Sesión") || result.error?.includes("sesión")
                      ? "inicie sesión de nuevo para buscar en internet."
                      : `no pude obtener la información. ${result.error || "Inténtelo de nuevo."}`;
              narrate(spoken);
            }
          } catch (err) {
            cedVoiceLog(4, "Web search network error", { err: String(err) });
            narrate(
              "no pude contactar el buscador. Verifique que la API esté corriendo con pnpm dev:api.",
            );
          } finally {
            if (!narrated && !isStale()) {
              narrate("no obtuve respuesta del buscador.");
            }
            webFetchRef.current = false;
            clientWebSearchRef.current = false;
            if (!succeeded) lastWebQueryRef.current = "";
          }
        })();
      };

      const handleSearchStatus = (_text: string) => {
        if (webFetchRef.current) return;
        const retry = lastWebQueryRef.current.trim();
        if (retry && isWebResearchIntent(retry)) {
          runWebSearch(retry);
          return;
        }
        client.sendNarrationBrief(
          "Indícame qué quieres buscar y lo consulto en internet.",
        );
      };

      const runVisualSearch = (question = "") => {
        const frame = captureCameraJpeg();
        if (!frame || webFetchRef.current || isStale()) {
          if (!frame) {
            client.sendNarrationBrief(
              "active la cámara primero para buscar lo que veo.",
            );
          }
          return;
        }
        cedVoiceLog(5, "Visual web search", { q: question.slice(0, 60) });
        webFetchRef.current = true;
        setOrbState("processing");
        setStatusLabel("Buscando en internet…");
        void (async () => {
          try {
            const result = await fetchVisionWebSearch(frame, question);
            if (isStale()) return;
            if (result.ok) {
              cedVoiceLog(6, "Visual search ok", { len: result.summary.length });
              client.sendNarrationBrief(result.summary);
              if (result.query) {
                schedulePanelSearch(result.query, "general");
              }
            } else {
              client.sendNarrationBrief(
                result.code === "missing_tavily"
                  ? "configure Tavily en el servidor para buscar lo que veo."
                  : `no pude buscar en internet: ${result.error}`,
              );
            }
          } catch {
            client.sendNarrationBrief(
              "falló la búsqueda visual. Inténtelo de nuevo.",
            );
          } finally {
            webFetchRef.current = false;
          }
        })();
      };

      const handleClientVoiceIntents = (text: string) => {
        const t = text.trim();
        if (!t) return;

        if (isVisualSearchIntent(t) && cameraStreamRef.current) {
          runVisualSearch(t);
          return;
        }
        if (isRememberIntent(t)) {
          const parsed = parseRememberContent(t);
          if (parsed) {
            void saveMemory(parsed.key, parsed.content).then((r) => {
              if (!isStale()) {
                client.sendNarrationBrief(
                  r.ok
                    ? "lo guardé en memoria cognitiva."
                    : "no pude guardar en memoria.",
                );
              }
            });
          }
          return;
        }
        if (isMemoryRecallIntent(t)) {
          void searchMemory(t).then((r) => {
            if (isStale()) return;
            if (!r.ok || !r.results.length) {
              client.sendNarrationBrief("no encontré memorias sobre eso.");
              return;
            }
            const lines = r.results
              .slice(0, 3)
              .map((m) => `${m.key}: ${m.content}`)
              .join(". ");
            client.sendNarrationBrief(`recuerdo lo siguiente. ${lines}`);
          });
          return;
        }
      };

      const handlers: CedLiveHandlers = {
        onState: (s) => {
          if (isStale()) return;
          if (s === "connecting") {
            setOrbState("processing");
            setStatusLabel("Conectando con CED…");
          }
          if (s === "error") setOrbState("error");
        },
        onSessionReady: () => {
          if (setupTimerRef.current) {
            clearTimeout(setupTimerRef.current);
            setupTimerRef.current = null;
          }
          if (!greetingSentRef.current) {
            greetingSentRef.current = true;
            setStatusLabel("CED te saluda…");
            client.sendSessionGreeting();
          }
        },
        onTranscriptUpdate: (text, role) => {
          if (isStale() || role !== "user") return;
          const trimmed = text.trim();
          if (!trimmed || /^<noise>$/i.test(trimmed)) return;
          lastUserUtteranceRef.current = trimmed;
          if (webFetchRef.current) {
            setOrbState("processing");
            setStatusLabel("Buscando en internet…");
          }
          setHeardIndicator({
            status: "heard",
            userText: trimmed,
            heardAt: Date.now(),
          });
        },
        onTranscript: (text, role) => {
          if (isStale()) return;
          callbacks?.onTranscript?.(text, role);
          void persistMessage(role, text);
          if (role === "user") {
            modelRepliedTurnRef.current = false;
            const trimmed = text.trim();
            lastUserUtteranceRef.current = trimmed;
            if (isAdvancedConfirmAnswer(trimmed) && advancedConfirmPendingRef.current) {
              /* esperando que el modelo invoque la herramienta */
            } else if (
              isComplexAnalysisRequest(trimmed) ||
              isExplicitAdvancedRequest(trimmed)
            ) {
              advancedConfirmAskedRef.current = false;
              advancedConfirmPendingRef.current = false;
              pendingAdvancedPromptRef.current = "";
            } else if (!advancedConfirmPendingRef.current) {
              advancedConfirmAskedRef.current = false;
              pendingAdvancedPromptRef.current = "";
            }
            if (isSearchStatusIntent(text)) {
              handleSearchStatus(text.trim());
            } else if (isWebResearchIntent(text) && !webFetchRef.current) {
              const q = text.trim();
              if (webSearchDebounceRef.current) {
                clearTimeout(webSearchDebounceRef.current);
              }
              webSearchDebounceRef.current = window.setTimeout(() => {
                webSearchDebounceRef.current = null;
                if (webFetchRef.current || isStale()) return;
                if (lastUserUtteranceRef.current.trim() !== q) return;
                runWebSearch(q);
              }, 2600);
            } else {
              handleClientVoiceIntents(text.trim());
            }
          }
          if (role === "model") {
            modelRepliedTurnRef.current = true;
            setOrbState("speaking");
            setStatusLabel(ORB_STATE_LABELS.speaking);
            setHeardIndicator((prev) =>
              prev.status === "hidden"
                ? prev
                : { ...prev, status: "responding" },
            );
          }
        },
        onToolStart: (toolName) => {
          if (isStale()) return;
          if (toolName === CONSULTAR_SISTEMA_AVANZADO) {
            advancedConfirmPendingRef.current = false;
            advancedConfirmAskedRef.current = false;
            pendingAdvancedPromptRef.current = "";
          }
          modelSpeakingRef.current = true;
          setOrbState("processing");
          const labels: Record<string, string> = {
            search_web: "Buscando en internet…",
            [CONSULTAR_SISTEMA_AVANZADO]: "Consultando sistema avanzado…",
            [GUARDAR_MEMORIA]: "Guardando en memoria…",
            [BUSCAR_MEMORIA]: "Consultando memoria…",
            [ACTIVAR_PROSPECCION]: "Activando prospección…",
            [DESACTIVAR_PROSPECCION]: "Desactivando prospección…",
            [REPORTE_PROSPECCION]: "Generando reporte…",
            [PUBLICAR_FACEBOOK]: "Publicando en Facebook…",
            [PUBLICAR_INSTAGRAM]: "Publicando en Instagram…",
            [BUSCAR_LO_VISIBLE]: "Buscando lo que veo…",
            [GENERAR_PDF]: "Generando PDF…",
          };
          setStatusLabel(labels[toolName] ?? "Consultando…");
          scheduleResponseWatchdog();
        },
        onToolComplete: () => {
          if (isStale()) return;
          scheduleResponseWatchdog();
        },
        shouldAllowAdvancedTool: (toolPrompt) =>
          shouldAllowAdvancedTool(
            lastUserUtteranceRef.current,
            toolPrompt,
            webFetchRef.current,
            advancedConfirmPendingRef.current,
          ),
        onAdvancedToolBlocked: (toolPrompt) => {
          const q = toolPrompt.trim() || lastUserUtteranceRef.current.trim();
          if (
            q &&
            !webFetchRef.current &&
            (isWebResearchIntent(q) ||
              isWeatherIntent(q) ||
              isWebResearchIntent(lastUserUtteranceRef.current))
          ) {
            cedVoiceLog(5, "Tool blocked → web search", { q: q.slice(0, 80) });
            runWebSearch(q);
            return;
          }
          if (webFetchRef.current || advancedConfirmAskedRef.current) return;
          if (
            isExplicitAdvancedRequest(lastUserUtteranceRef.current) ||
            isExplicitAdvancedRequest(q)
          ) {
            return;
          }
          advancedConfirmAskedRef.current = true;
          advancedConfirmPendingRef.current = true;
          pendingAdvancedPromptRef.current = q;
          cedVoiceLog(5, "Sistema avanzado: esperando confirmación del usuario");
        },
        onLiveTool: async (name, args) => {
          if (name === GUARDAR_MEMORIA) {
            const key = String(args.clave ?? args.key ?? "nota").trim();
            const content = String(args.contenido ?? args.content ?? "").trim();
            if (!content) {
              return { spoken: "no recibí qué guardar en memoria." };
            }
            const r = await saveMemory(key, content, String(args.categoria ?? ""));
            return {
              spoken: r.ok
                ? "guardado en memoria cognitiva."
                : "no pude guardar en memoria.",
            };
          }
          if (name === BUSCAR_MEMORIA) {
            const q = String(args.consulta ?? args.query ?? "").trim();
            const r = await searchMemory(q);
            if (!r.ok || !r.results.length) {
              return { spoken: "no encontré memorias sobre eso." };
            }
            const lines = r.results
              .slice(0, 3)
              .map((m) => `${m.key}: ${m.content}`)
              .join(". ");
            return { spoken: `recuerdo: ${lines}` };
          }
          if (name === ACTIVAR_PROSPECCION) {
            const r = await enableProspection();
            return {
              spoken: r.ok
                ? "modo prospección activado. Escaneo comentarios en segundo plano."
                : "no pude activar prospección.",
            };
          }
          if (name === DESACTIVAR_PROSPECCION) {
            const r = await disableProspection();
            return {
              spoken: r.ok
                ? "prospección desactivada."
                : "no pude desactivar prospección.",
            };
          }
          if (name === REPORTE_PROSPECCION) {
            const r = await fetchProspectionReport();
            return {
              spoken: r.ok ? r.spoken : "no pude obtener el reporte.",
            };
          }
          if (name === PUBLICAR_FACEBOOK) {
            const message = String(
              args.mensaje ?? args.message ?? args.texto ?? "",
            ).trim();
            const imageUrl = String(args.image_url ?? args.imagen ?? "").trim();
            if (!message) {
              return {
                spoken:
                  "indíqueme el texto que desea publicar en Facebook.",
              };
            }
            const r = await publishFacebook(message, imageUrl || undefined);
            return {
              spoken: r.ok ? r.spoken : `${r.error}`,
            };
          }
          if (name === PUBLICAR_INSTAGRAM) {
            const caption = String(
              args.caption ?? args.mensaje ?? args.texto ?? "",
            ).trim();
            const imageUrl = String(args.image_url ?? args.imagen ?? "").trim();
            if (!caption || !imageUrl) {
              return {
                spoken:
                  "para Instagram necesito el texto y una URL pública HTTPS de la imagen.",
              };
            }
            const r = await publishInstagram(caption, imageUrl);
            return {
              spoken: r.ok ? r.spoken : `${r.error}`,
            };
          }
          if (name === BUSCAR_LO_VISIBLE) {
            const frame = captureCameraJpeg();
            if (!frame) {
              return {
                spoken: "active la cámara para buscar lo que veo.",
              };
            }
            const pregunta = String(args.pregunta ?? args.question ?? "").trim();
            const result = await fetchVisionWebSearch(frame, pregunta);
            if (result.ok) {
              if (result.query) schedulePanelSearch(result.query, "general");
              return { spoken: result.summary };
            }
            return {
              spoken:
                result.code === "missing_tavily"
                  ? "configure Tavily para búsqueda visual."
                  : `no pude buscar: ${result.error}`,
            };
          }
          if (name === GENERAR_PDF) {
            const title = String(args.titulo ?? args.title ?? "Documento CED").trim();
            let content = String(args.contenido ?? args.content ?? "").trim();
            if (!content) content = title;
            const cid = conversationRef.current;
            try {
              const pdf = await generatePdf(title, content, cid);
              return {
                spoken: `Listo. PDF "${pdf.title}" guardado en tu historial.`,
              };
            } catch {
              return { spoken: "no pude generar el PDF. Intenta de nuevo." };
            }
          }
          return { spoken: "herramienta no reconocida." };
        },
        onResponseStart: () => {
          if (isStale()) return;
          lastResponseStartRef.current = Date.now();
          modelSpeakingRef.current = true;
          modelRepliedTurnRef.current = true;
          clearResponseWatchdog();
          scheduleResponseWatchdog();
          setOrbState("speaking");
          setStatusLabel(ORB_STATE_LABELS.speaking);
          setHeardIndicator((prev) =>
            prev.status === "hidden"
              ? prev
              : { ...prev, status: "responding" },
          );
        },
        onInterrupted: () => {
          cedVoiceLog(5, "OpenAI interrupted");
          clearResponseWatchdog();
          modelSpeakingRef.current = false;
          client.setMicTrackEnabled(!pausedRef.current);
          setErrorMessage((prev) =>
            prev && isBenignRealtimeError(prev) ? null : prev,
          );
          if (micActiveRef.current) {
            enableListeningUi();
          }
        },
        onSpeechStopped: () => {
          if (isStale() || pausedRef.current) return;
          setHeardIndicator((prev) =>
            prev.status === "hidden"
              ? prev
              : { ...prev, status: "heard", heardAt: Date.now() },
          );
          if (!modelSpeakingRef.current) {
            setOrbState("processing");
            setStatusLabel(ORB_STATE_LABELS.processing);
            clearResponseWatchdog();
            responseWatchdogRef.current = window.setTimeout(() => {
              responseWatchdogRef.current = null;
              if (isStale() || !micActiveRef.current) return;
              if (!modelSpeakingRef.current && !client.isResponseActive()) {
                enableListeningUi();
              }
            }, PROCESSING_STUCK_MS);
          }
        },
        onTurnComplete: () => {
          clearResponseWatchdog();
          modelSpeakingRef.current = false;
          if (!pausedRef.current) {
            client.setMicTrackEnabled(true);
          }
          client.flushInputAudioBuffer();
          setHeardIndicator((prev) => {
            if (prev.status === "hidden") return prev;
            if (!modelRepliedTurnRef.current && prev.userText) {
              return { ...prev, status: "no_voice_reply" };
            }
            if (prev.userText) return { ...prev, status: "heard" };
            return { ...prev, status: "listening" };
          });
          modelRepliedTurnRef.current = false;
          if (micActiveRef.current) {
            enableListeningUi();
          }
        },
        onCameraIntent: (intent) => {
          void toggleCameraRef.current(intent === "activate");
        },
        onError: (msg) => {
          if (isBenignRealtimeError(msg)) return;
          setErrorMessage(msg);
          setOrbState("error");
          setStatusLabel(ORB_STATE_LABELS.error);
        },
        onClose: (info) => {
          if (isStale() || !info.unexpected || !micActiveRef.current) return;

          if (!info.recoverable) {
            setErrorMessage(
              info.userMessage ??
                "OpenAI cerró la sesión. Revisa tu API key y saldo.",
            );
            setOrbState("error");
            void stopSession();
            return;
          }
          if (reconnectAttemptRef.current >= MAX_WS_RECONNECT) {
            setErrorMessage(
              "Conexión con CED perdida. Desactiva y vuelve a activar el micrófono.",
            );
            setOrbState("error");
            void stopSession();
            return;
          }

          reconnectAttemptRef.current += 1;
          const attempt = reconnectAttemptRef.current;
          setOrbState("processing");
          setStatusLabel(`Reconectando con CED (${attempt}/${MAX_WS_RECONNECT})…`);

          window.setTimeout(() => {
            if (isStale() || !micActiveRef.current) return;
            const h = handlersRef.current;
            if (!h) return;
            void (async () => {
              const stream = micStreamRef.current;
              if (!stream) return;
              const ok = await client.connect(h, {
                voiceName: prefsRef.current.voiceName,
                language: prefsRef.current.language,
                responseSpeed: prefsRef.current.responseSpeed,
                micStream: stream,
              });
              if (ok) {
                reconnectAttemptRef.current = 0;
                client.setRemoteMuted(mutedRef.current);
                client.setMicTrackEnabled(!pausedRef.current);
              } else if (reconnectAttemptRef.current >= MAX_WS_RECONNECT) {
                setErrorMessage("No se pudo reconectar con CED.");
                setOrbState("error");
                void stopSession();
              }
            })();
          }, 1000 * attempt);
        },
      };

      handlersRef.current = handlers;
      if (isStale()) return;

      voiceTelemetry.setActiveVoice(prefsRef.current.voiceName);
      const ok = await client.connect(handlers, {
        voiceName: prefsRef.current.voiceName,
        language: prefsRef.current.language,
        responseSpeed: prefsRef.current.responseSpeed,
        micStream: stream,
      });

      if (!ok) await stopSession();
      else {
        reconnectAttemptRef.current = 0;
        setupTimerRef.current = window.setTimeout(() => {
          if (isStale() || greetingSentRef.current) return;
          setErrorMessage(
            "OpenAI no respondió a tiempo. Desactiva el micrófono y vuelve a intentar.",
          );
          setOrbState("error");
          void stopSession();
        }, 22000);
      }
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      let msg =
        err instanceof Error
          ? err.message
          : "Permite el acceso al micrófono para hablar con CED.";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        msg =
          "Permiso de micrófono denegado. Actívalo en el candado de la barra del navegador.";
      } else if (name === "NotFoundError") {
        msg = "No se detectó ningún micrófono en este dispositivo.";
      }
      setErrorMessage(msg);
      setOrbState("error");
      await stopSession();
    } finally {
      setMicBusy(false);
    }
  }, [
    micOn,
    micBusy,
    stopSession,
    persistMessage,
    onUsageRefresh,
    callbacks,
  ]);

  useEffect(() => {
    clientRef.current?.setRemoteMuted(muted);
  }, [muted]);

  useEffect(() => {
    if (!micOn) return;
    clientRef.current?.setMicTrackEnabled(!paused);
  }, [micOn, paused]);

  useEffect(() => {
    return () => {
      voiceSessionGenRef.current += 1;
      clientRef.current?.disconnect();
      clearUsageInterval();
    };
  }, [clearUsageInterval]);

  useEffect(() => {
    if (!cameraOn || !cameraStreamRef.current) return;

    const video = document.createElement("video");
    video.srcObject = cameraStreamRef.current;
    video.muted = true;
    video.playsInline = true;
    cameraCaptureVideoRef.current = video;

    let cancelled = false;
    let frameCallbackId = 0;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;

    const maybeSendFrame = () => {
      if (cancelled || pausedRef.current || !micOnRef.current) return;
      const now = Date.now();
      if (now - lastVideoSentRef.current < VIDEO_SEND_INTERVAL_MS) return;
      const dataUrl = captureCameraJpeg();
      if (!dataUrl) return;
      lastVideoSentRef.current = now;
      clientRef.current?.sendVideoJpeg(dataUrl);
      resetCameraIdleTimer();
    };

    const onVideoFrame = () => {
      if (cancelled) return;
      maybeSendFrame();
      if ("requestVideoFrameCallback" in video) {
        frameCallbackId = video.requestVideoFrameCallback(onVideoFrame);
      }
    };

    void video.play().then(() => {
      if (cancelled) return;
      if ("requestVideoFrameCallback" in video) {
        frameCallbackId = video.requestVideoFrameCallback(onVideoFrame);
      } else {
        fallbackTimer = setInterval(maybeSendFrame, VIDEO_SEND_INTERVAL_MS);
      }
    });

    return () => {
      cancelled = true;
      if (fallbackTimer) clearInterval(fallbackTimer);
      if (frameCallbackId && "cancelVideoFrameCallback" in video) {
        video.cancelVideoFrameCallback(frameCallbackId);
      }
      video.srcObject = null;
      if (cameraCaptureVideoRef.current === video) {
        cameraCaptureVideoRef.current = null;
      }
    };
  }, [cameraOn, captureCameraJpeg, resetCameraIdleTimer]);

  const togglePause = useCallback(() => {
    setPaused((p) => {
      const next = !p;
      clientRef.current?.setMicTrackEnabled(!next);
      setOrbState(next ? "paused" : micOn ? "listening" : "idle");
      setStatusLabel(
        next ? ORB_STATE_LABELS.paused : ORB_STATE_LABELS.listening,
      );
      return next;
    });
  }, [micOn]);

  const updatePrefs = useCallback((next: VoiceSessionPreferences) => {
    setPrefs(next);
    saveVoicePreferences(next);
    prefsRef.current = next;
  }, []);

  const applyVoiceChange = useCallback(
    async (voiceName: string) => {
      const normalized = normalizeVoiceName(voiceName);
      const next = { ...prefsRef.current, voiceName: normalized };
      setPrefs(next);
      saveVoicePreferences(next);
      prefsRef.current = next;
      voiceTelemetry.markVoiceChange(normalized);

      if (!micOn || !handlersRef.current || !clientRef.current) return;

      setOrbState("processing");
      setStatusLabel("Cambiando voz…");

      const stream = micStreamRef.current;
      if (!stream) return;

      const ok = await clientRef.current.connect(handlersRef.current, {
        voiceName: normalized,
        language: prefsRef.current.language,
        responseSpeed: prefsRef.current.responseSpeed,
        micStream: stream,
      });

      if (ok) {
        clientRef.current.setRemoteMuted(mutedRef.current);
        setOrbState("listening");
        setStatusLabel(`Voz activa: ${normalized}`);
        window.setTimeout(() => {
          setStatusLabel(ORB_STATE_LABELS.listening);
        }, 2000);
      } else {
        setErrorMessage("No se pudo cambiar la voz. Intenta de nuevo.");
      }
    },
    [micOn],
  );

  const clearError = useCallback(() => {
    setErrorMessage(null);
    setOrbState((s) => (s === "error" ? "idle" : s));
    setStatusLabel(ORB_STATE_LABELS.idle);
  }, []);

  return {
    orbState,
    statusLabel,
    audioLevel,
    micOn,
    cameraOn,
    muted,
    paused,
    prefs,
    historyOpen,
    setHistoryOpen,
    settingsOpen,
    setSettingsOpen,
    stopConfirmOpen,
    setStopConfirmOpen,
    cameraStream,
    errorMessage,
    heardIndicator,
    micBusy,
    inputLevel,
    toggleMic,
    toggleCamera,
    togglePause,
    setMuted,
    stopSession,
    updatePrefs,
    applyVoiceChange,
    clearError,
  };
}
