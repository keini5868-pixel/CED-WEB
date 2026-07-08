"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { OrbState, VoiceSessionPreferences } from "@ced/types";
import { ORB_STATE_LABELS } from "@ced/types";

import { appendConversationMessage } from "@/lib/api/conversations";
import { normalizeCedMediaUrl } from "@/lib/api/media-url";
import { generatePdf } from "@/lib/api/pdf";
import { fetchVoiceBrief, fetchGenerateImage, fetchGenerateImageWithReference, fetchDeepAnalysis } from "@/lib/api/openai";
import { saveMemory, searchMemory, recallPreviousConversations, saveLongTermMemory } from "@/lib/api/memory";
import { updateUserAddress } from "@/lib/api/profile";
import { schedulePanelSearch } from "@/lib/api/panels";
import {
  disableProspection,
  enableProspection,
  fetchProspectionReport,
} from "@/lib/api/prospection";
import { publishFacebook, publishInstagram, fetchSocialComments } from "@/lib/api/social";
import { fetchVisionAnalyze, fetchVisionWebSearch } from "@/lib/api/vision";
import {
  ackVoiceClientAction,
  fetchVoiceClientState,
  postVoiceCameraStatus,
  postVoiceCameraPermission,
  postVoiceChatImage,
  postVoiceSessionEnd,
  postVoiceVisionResult,
} from "@/lib/api/voiceClient";
import type { NavClientAction } from "@/lib/api/navigation";
import {
  endVoiceSession,
  startVoiceSession,
  tickVoiceSessionDetailed,
} from "@/lib/api/usage";
import { useAudioAnalyser } from "@/hooks/useAudioAnalyser";
import { useDriveMap } from "@/contexts/DriveMapContext";
import { unlockVoiceAudioOnGesture } from "@/lib/voice/live/audio-context";
import { clearEphemeralTokenCache } from "@/lib/voice/ephemeralTokenCache";
import {
  isAddressPreferenceIntent,
  parseAddressPreference,
  parseGenderPreference,
} from "@/lib/voice/addressPreferenceIntent";
import {
  isCasualSocialGreeting,
  isStandaloneHonorificPreference,
} from "@/lib/voice/voiceSmallTalk";
import {
  CedLiveClient,
  type CedLiveHandlers,
} from "@/lib/voice/live/ced-live-client";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import {
  cedIdlePresencePhrase,
  cedPublishFailurePhrase,
  cedPublishSuccessPhrase,
  cedResolveHonorific,
} from "@/lib/voice/live/ced-brief-messages";
import { cedVoiceLog } from "@/lib/voice/cedVoiceLogger";
import { registerRetellCall, warmupRetellVoiceApi } from "@/lib/api/retell";
import { CedRetellClient } from "@/lib/voice/retell/ced-retell-client";
import { isRetellVoice } from "@/lib/voice/voiceProvider";
import { isBenignRealtimeError } from "@/lib/voice/realtimeErrors";
import { normalizeVoiceName } from "@/lib/voice/openaiVoices";
import {
  LEER_COMENTARIOS_REDES,
  ACTIVAR_PROSPECCION,
  ANALIZAR_CAMARA,
  BUSCAR_LO_VISIBLE,
  BUSCAR_MEMORIA,
  CONSULTAR_SISTEMA_AVANZADO,
  DESACTIVAR_PROSPECCION,
  GUARDAR_MEMORIA,
  REPORTE_PROSPECCION,
  PUBLICAR_FACEBOOK,
  PUBLICAR_INSTAGRAM,
  GENERAR_PDF,
  RECALL_PREVIOUS_CONVERSATIONS,
  SAVE_LONG_TERM_MEMORY,
} from "@/lib/voice/liveTools";
import { isAdvancedConfirmAnswer, isComplexAnalysisRequest, isExplicitAdvancedRequest, isSearchStatusIntent, isWeatherIntent, isWebResearchIntent, shouldAllowAdvancedTool, webBriefKind, webBriefTimeoutMs } from "@/lib/voice/webResearchIntent";
import {
  isMemoryRecallIntent,
  isRememberIntent,
  isVisualSearchIntent,
  parseRememberContent,
  userExplicitlyRequestedProspection,
} from "@/lib/voice/visualSearchIntent";
import {
  cameraAnalyzeQuestion,
  isCameraAnalyzeIntent,
} from "@/lib/voice/cameraAnalyzeIntent";
import { parseCameraIntent } from "@/lib/voice/cameraIntents";
import {
  parseFacebookPublishMessage,
  parseDirectPublishContent,
  parseInstagramPublishRequest,
  isPublishRequestWithoutContent,
  isPublishPlanningIntent,
  parsePublishIdea,
  isPublishGoCommand,
  isPublishDirectCommand,
  detectPublishPlatform,
  isSocialPublishIntent,
  type PublishPlatform,
} from "@/lib/voice/socialPublishIntent";
import {
  isGenerateImageIntent,
  parseGenerateImagePrompt,
  wantsCameraImageForPublish,
  wantsLastImageForPublish,
} from "@/lib/voice/imageIntents";
import { isPdfIntent, parsePdfRequest } from "@/lib/voice/pdfIntents";
import { voiceTelemetry } from "@/lib/voice/voiceTelemetry";
import {
  loadVoicePreferences,
  saveMicPreference,
  saveVoicePreferences,
} from "@/lib/voice/preferences";

const CAMERA_IDLE_MS = 5 * 60 * 1000;
const CAMERA_FRAME_WARM_MS = 4500;
const CAMERA_FRAME_READY_MS = 1200;
const VOICE_CLIENT_POLL_MS = 300;
const VIDEO_SEND_INTERVAL_MS = 2000;
const VIDEO_CAPTURE_WIDTH = 640;
const VIDEO_CAPTURE_HEIGHT = 480;
const VISION_CAPTURE_WIDTH = 480;
const VISION_CAPTURE_HEIGHT = 360;
const USAGE_TICK_SECONDS = 15;
const MAX_WS_RECONNECT = 3;
/** Si el turno no cierra, liberar mic/UI (WebRTC). */
const TURN_STUCK_MS = 22000;
const PROCESSING_STUCK_MS = 12000;
const MIC_UNMUTE_AFTER_SPEECH_MS = 2200;
const MIC_UNMUTE_AFTER_GREETING_MS = 4500;
/** Tras saludo sin respuesta del usuario — una sola frase de presencia. */
const IDLE_PRESENCE_MS = 50_000;

function bindHudCameraFeed(stream: MediaStream): boolean {
  const videoEl = document.querySelector<HTMLVideoElement>("#ced-camera-feed");
  if (!videoEl) return false;
  if (videoEl.srcObject !== stream) {
    videoEl.srcObject = stream;
  }
  void videoEl.play().catch(() => undefined);
  return true;
}

const CAMERA_VIDEO_CONSTRAINTS: MediaTrackConstraints = {
  facingMode: { ideal: "environment" },
  width: { ideal: 1280 },
  height: { ideal: 720 },
  frameRate: { ideal: 24, max: 30 },
};

const CAMERA_PRIVACY_SPOKEN =
  "Cámara activa, señor. Solo yo puedo ver lo que me muestra. Nadie más tiene acceso.";

const CAMERA_PERMISSION_DENIED_SPOKEN =
  "No pude activar la cámara. Necesito su permiso, señor.";

function requestCameraMediaStream(
  constraints: MediaTrackConstraints = CAMERA_VIDEO_CONSTRAINTS,
): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    return Promise.reject(new Error("getUserMedia unavailable"));
  }
  return navigator.mediaDevices.getUserMedia({ video: constraints });
}

async function publishImageToBlob(image: {
  imageUrl?: string;
  imageData?: string;
}): Promise<Blob | null> {
  const data = String(image.imageData ?? "").trim();
  if (data) {
    const res = await fetch(data);
    return res.blob();
  }
  const url = String(image.imageUrl ?? "").trim();
  if (url) {
    const res = await fetch(normalizeCedMediaUrl(url));
    return res.blob();
  }
  return null;
}

export interface CedVoiceSessionCallbacks {
  onTranscript?: (
    text: string,
    role: "user" | "model",
    options?: { partial?: boolean; streamKey?: string },
  ) => void;
  /** Imagen generada (voz) — abrir chat / preview */
  onGeneratedImage?: (url: string, prompt?: string) => void;
  /** Retracta bubble agent en HUD al interrumpir (Retell). */
  onClearAgentPartial?: () => void;
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
  const [retellPollActive, setRetellPollActive] = useState(false);
  const [voiceSessionActive, setVoiceSessionActive] = useState(false);
  const lastVoiceActionIdRef = useRef<number | null>(null);
  const lastCameraHeartbeatRef = useRef(0);
  const lastToolEventIdRef = useRef(0);
  const [cameraOn, setCameraOn] = useState(false);
  const [muted, setMuted] = useState(false);
  const [paused, setPaused] = useState(false);
  const [prefs, setPrefs] = useState<VoiceSessionPreferences>(loadVoicePreferences);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [cameraPermissionGranted, setCameraPermissionGranted] = useState(false);
  const [cameraFacing, setCameraFacing] = useState<"user" | "environment">("user");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [heardIndicator, setHeardIndicator] =
    useState<VoiceHeardIndicator>(INITIAL_HEARD);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [micBusy, setMicBusy] = useState(false);
  const { openDriveMap, isOpen: isDriveMapOpen } = useDriveMap();
  const isDriveMapOpenRef = useRef(isDriveMapOpen);
  const openDriveMapRef = useRef(openDriveMap);
  const micBusyRef = useRef(false);

  const micStreamRef = useRef<MediaStream | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const cameraFacingRef = useRef<"user" | "environment">("user");
  const cameraActivateInFlightRef = useRef<Promise<void> | null>(null);
  const cameraPermissionGrantedRef = useRef(false);
  const sessionMediaPreauthRef = useRef<Promise<void> | null>(null);
  const activateCameraFromVoiceRef = useRef<
    (opts?: {
      ackActionId?: number;
      showFeedback?: boolean;
    }) => Promise<void>
  >(async () => undefined);
  const cameraIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clientRef = useRef<CedLiveClient | null>(null);
  const retellClientRef = useRef<CedRetellClient | null>(null);
  const isRetellSessionRef = useRef(false);
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
  const recentAssistantTextsRef = useRef<string[]>([]);
  const advancedConfirmPendingRef = useRef(false);
  const advancedConfirmAskedRef = useRef(false);
  const pendingAdvancedPromptRef = useRef("");
  const pendingPublishRef = useRef<{
    platform: PublishPlatform;
    awaiting: "develop" | "confirm";
    draftText?: string;
  } | null>(null);
  const webSearchDebounceRef = useRef<number | null>(null);
  const cameraPreviewRef = useRef<string | null>(null);
  const lastPublishableImageRef = useRef<string | null>(null);
  const cameraCaptureVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraCaptureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const micOnRef = useRef(micOn);
  const userInitiatedStopRef = useRef(false);
  const retellCallStartedAtRef = useRef(0);
  const retellEarlyEndRetriesRef = useRef(0);
  const lastPersistedAgentLineRef = useRef("");

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

  const persistMessage = useCallback(
    async (role: "user" | "model", text: string) => {
      const cid = conversationRef.current;
      if (!cid || !text.trim()) return;
      try {
        await appendConversationMessage(
          cid,
          role,
          text,
          usageSessionRef.current ?? undefined,
        );
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const persistVoiceTranscript = useCallback(
    (
      role: "user" | "model",
      text: string,
      options?: { partial?: boolean },
    ) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      if (role === "model" && options?.partial) return;
      if (role === "model") {
        if (trimmed === lastPersistedAgentLineRef.current) return;
        lastPersistedAgentLineRef.current = trimmed;
      }
      void persistMessage(role, trimmed);
    },
    [persistMessage],
  );

  useEffect(() => {
    if (!isRetellVoice()) return;
    void warmupRetellVoiceApi();
  }, []);

  const captureCameraJpeg = useCallback((compact = false): string | null => {
    const video = cameraCaptureVideoRef.current;
    if (!video || video.videoWidth === 0) {
      return compact ? null : cameraPreviewRef.current;
    }
    let canvas = cameraCaptureCanvasRef.current;
    if (!canvas) {
      canvas = document.createElement("canvas");
      cameraCaptureCanvasRef.current = canvas;
    }
    canvas.width = compact ? VISION_CAPTURE_WIDTH : VIDEO_CAPTURE_WIDTH;
    canvas.height = compact ? VISION_CAPTURE_HEIGHT : VIDEO_CAPTURE_HEIGHT;
    const ctx = canvas.getContext("2d");
    ctx?.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", compact ? 0.62 : 0.72);
    if (!compact) cameraPreviewRef.current = dataUrl;
    return dataUrl;
  }, []);

  const waitForCameraFrame = useCallback(
    async (maxMs = 2400, compact = false): Promise<string | null> => {
      const frame = captureCameraJpeg(compact);
      if (frame) return frame;
      const started = Date.now();
      while (Date.now() - started < maxMs) {
        await new Promise((r) => window.setTimeout(r, 80));
        const next = captureCameraJpeg(compact);
        if (next) return next;
      }
      return captureCameraJpeg(compact);
    },
    [captureCameraJpeg],
  );

  useEffect(() => {
    isDriveMapOpenRef.current = isDriveMapOpen;
    openDriveMapRef.current = openDriveMap;
  }, [isDriveMapOpen, openDriveMap]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const active = voiceSessionActive || micOn;
    if (active) {
      window.sessionStorage.setItem("ced-voice-active", "1");
      document.body.setAttribute("data-ced-voice-active", "true");
    } else {
      window.sessionStorage.removeItem("ced-voice-active");
      document.body.removeAttribute("data-ced-voice-active");
    }
  }, [voiceSessionActive, micOn]);

  useEffect(() => {
    if (!retellPollActive) return;

    let cancelled = false;

    const cameraStreamLive = (): boolean => {
      const stream = cameraStreamRef.current;
      return !!(
        stream?.active &&
        stream.getVideoTracks().some((t) => t.readyState === "live" && t.enabled)
      );
    };

    const waitForCameraStream = async (maxMs = 4500): Promise<boolean> => {
      const started = Date.now();
      while (Date.now() - started < maxMs) {
        if (cameraStreamLive()) return true;
        await new Promise((r) => window.setTimeout(r, 120));
      }
      return cameraStreamLive();
    };

    const ensureCameraCaptureVideo = async (maxMs = 5000): Promise<boolean> => {
      const stream = cameraStreamRef.current;
      if (!stream) return false;
      let video = cameraCaptureVideoRef.current;
      if (!video || video.srcObject !== stream) {
        video = document.createElement("video");
        video.srcObject = stream;
        video.muted = true;
        video.playsInline = true;
        cameraCaptureVideoRef.current = video;
        await video.play().catch(() => undefined);
      }
      const started = Date.now();
      while (Date.now() - started < maxMs) {
        if (video.videoWidth > 0) return true;
        await new Promise((r) => window.setTimeout(r, 80));
      }
      return video.videoWidth > 0;
    };

    const handleVoiceClientAction = async (action: {
      id: number;
      action: string;
      payload: Record<string, unknown>;
    }) => {
      if (action.action === "camera_activate") {
        console.log("[CAMERA] poll activate action_id=%s", action.id);
        await activateCameraFromVoiceRef.current({
          ackActionId: action.id,
          showFeedback: false,
        });
        return;
      }
      if (action.action === "camera_deactivate") {
        await toggleCameraRef.current(false);
        await postVoiceCameraStatus(false, false);
        await ackVoiceClientAction(action.id);
        return;
      }
      if (action.action !== "camera_capture") return;

      const requestId = Number(action.payload.request_id || 0);
      const question = String(action.payload.question || "");
      const mode = String(action.payload.mode || "analyze");
      console.log("[CAMERA] poll capture request_id=%s mode=%s", requestId, mode);
      if (!requestId) {
        await ackVoiceClientAction(action.id);
        return;
      }

      try {
        const hadStream =
          !!cameraStreamRef.current?.active &&
          cameraStreamRef.current
            .getVideoTracks()
            .some((t) => t.readyState === "live" && t.enabled);
        if (!hadStream) {
          await toggleCameraRef.current(true);
          await waitForCameraStream();
        }
        const streamLive = cameraStreamLive();
        await postVoiceCameraStatus(streamLive, streamLive);
        await ensureCameraCaptureVideo(hadStream ? 2000 : 5000);
        const frame = await waitForCameraFrame(
          hadStream ? CAMERA_FRAME_READY_MS : CAMERA_FRAME_WARM_MS,
          mode === "analyze",
        );
        if (!frame) {
          console.warn("[VISION:GEMINI] empty_frame request_id=%s", requestId);
          await postVoiceVisionResult(
            requestId,
            "Señor, no pude procesar la imagen de la cámara. Intente mostrar de nuevo.",
          );
        } else {
          console.log("[VISION:GEMINI] analyze_start request_id=%s mode=%s", requestId, mode);
          const result =
            mode === "visual_search"
              ? await fetchVisionWebSearch(frame, question)
              : await fetchVisionAnalyze(
                  frame,
                  question || "¿Qué ves en la imagen?",
                );
          console.log(
            "[VISION:GEMINI] analyze_done request_id=%s ok=%s",
            requestId,
            result.ok,
          );
          await postVoiceVisionResult(
            requestId,
            result.ok ? result.summary : `No pude analizar: ${result.error}`,
          );
        }
      } catch (err) {
        console.error("[VISION:GEMINI] analyze_error request_id=%s", requestId, err);
        await postVoiceVisionResult(requestId, "Falló el análisis de cámara.");
      }
      await ackVoiceClientAction(action.id);
    };

    const poll = async () => {
      if (cancelled) return;
      try {
        const now = Date.now();
        const streamLive = cameraStreamLive();
        if (streamLive && now - lastCameraHeartbeatRef.current > 12_000) {
          lastCameraHeartbeatRef.current = now;
          void postVoiceCameraStatus(true, true).catch(() => undefined);
        } else if (!streamLive && cameraOn && now - lastCameraHeartbeatRef.current > 12_000) {
          lastCameraHeartbeatRef.current = now;
          void postVoiceCameraStatus(false, false).catch(() => undefined);
        }
        const state = await fetchVoiceClientState(false);
        const events = state.tool_events ?? [];
        for (const ev of events) {
          const id = Number(ev.id || 0);
          if (!id || id <= lastToolEventIdRef.current) continue;
          lastToolEventIdRef.current = id;
          if (ev.type === "generated_image" && ev.image_url) {
            const normalized = normalizeCedMediaUrl(ev.image_url);
            lastPublishableImageRef.current = normalized;
            callbacks?.onGeneratedImage?.(normalized, ev.prompt);
          }
          if (ev.type === "pdf_created" && ev.title) {
            callbacks?.onTranscript?.(
              `PDF listo, señor. Título: ${String(ev.title)}. Ya está en su historial.`,
              "model",
              { partial: false },
            );
            void persistVoiceTranscript("model", `PDF generado: ${String(ev.title)}`);
          }
          if (ev.type === "camera_activate") {
            activateCameraFromVoiceRef.current({ showFeedback: false });
          }
          if (ev.type === "navigation_instruction" && ev.text) {
            const text = String(ev.text);
            window.dispatchEvent(
              new CustomEvent("ced-navigation-voice", {
                detail: { text },
              }),
            );
          }
          if (ev.type === "module_activated" && ev.module) {
            window.dispatchEvent(
              new CustomEvent("ced-module-active", {
                detail: { module: String(ev.module) },
              }),
            );
          }
          if (ev.type === "module_deactivated") {
            window.dispatchEvent(
              new CustomEvent("ced-module-active", {
                detail: { module: null },
              }),
            );
          }
          if (ev.type === "map_search_results" || ev.type === "map_start_navigation") {
            console.log("[MAP] tool_event recibido:", ev.type, ev);
          }
          if (ev.type === "camera_deactivate") {
            console.log("[CAMERA] tool_event recibido:", ev.type, ev);
            void toggleCameraRef.current(false);
            void postVoiceCameraStatus(false, false);
          }
          if (ev.type === "map_search_results" && ev.places) {
            window.dispatchEvent(
              new CustomEvent("ced-navigation-event", {
                detail: {
                  action: "show_place_options",
                  payload: {
                    query: ev.query || "",
                    places: ev.places,
                  },
                },
              }),
            );
          }
          if (ev.type === "map_start_navigation") {
            const navAction =
              ev.action === "begin_navigation" ? "begin_navigation" : "apply_route";
            const detail: NavClientAction = {
              id: Number(ev.id || Date.now()),
              action: navAction,
              payload:
                navAction === "apply_route" && ev.route
                  ? (ev.route as unknown as Record<string, unknown>)
                  : {},
            };
            if (!isDriveMapOpenRef.current) {
              openDriveMapRef.current(detail);
            } else {
              window.dispatchEvent(
                new CustomEvent("ced-navigation-event", { detail }),
              );
            }
          }
        }
        const action = state.client_action;
        if (!action || action.id === lastVoiceActionIdRef.current) return;
        lastVoiceActionIdRef.current = action.id;
        await handleVoiceClientAction(action);
      } catch {
        /* sin sesión */
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), VOICE_CLIENT_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [retellPollActive, waitForCameraFrame, callbacks, persistVoiceTranscript]);

  const resolvePublishImage = useCallback(
    async (
      args: Record<string, unknown>,
      userText = "",
    ): Promise<{ imageUrl?: string; imageData?: string }> => {
      const explicitData = String(args.image_data ?? args.imageData ?? "").trim();
      if (explicitData) {
        if (explicitData.startsWith("http")) return { imageUrl: explicitData };
        return { imageData: explicitData };
      }

      const useCamera =
        args.from_camera === true ||
        args.fromCamera === true ||
        wantsCameraImageForPublish(userText);
      if (useCamera) {
        if (!cameraStreamRef.current) {
          await toggleCameraRef.current(true);
        }
        const frame = await waitForCameraFrame(CAMERA_FRAME_WARM_MS);
        if (frame) return { imageData: frame };
      }

      const useLast =
        args.use_last_image === true ||
        args.useLastImage === true ||
        wantsLastImageForPublish(userText);
      if (useLast && lastPublishableImageRef.current) {
        const last = lastPublishableImageRef.current;
        if (last.startsWith("http")) return { imageUrl: last };
        return { imageData: last };
      }

      const url = String(args.image_url ?? args.imagen ?? "").trim();
      if (url) {
        if (url.startsWith("http")) return { imageUrl: url };
        return { imageData: url };
      }

      if (lastPublishableImageRef.current) {
        const last = lastPublishableImageRef.current;
        if (last.startsWith("http")) return { imageUrl: last };
        return { imageData: last };
      }

      return {};
    },
    [waitForCameraFrame],
  );

  const [retellInputLevel, setRetellInputLevel] = useState(0);
  const inputLevelFromMic = useAudioAnalyser(
    micStream,
    micOn && !paused && !isRetellVoice(),
  );
  const inputLevelRef = useRef(0);
  useEffect(() => {
    inputLevelRef.current = isRetellVoice() ? retellInputLevel : inputLevelFromMic;
  }, [retellInputLevel, inputLevelFromMic]);
  const inputLevel = isRetellVoice() ? retellInputLevel : inputLevelFromMic;
  const audioLevel =
    orbState === "listening"
      ? inputLevel
      : orbState === "speaking"
        ? 0.4
        : orbState === "processing"
          ? 0.5
          : 0.15;

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
      clientRef.current?.detachCameraStream();
      const stream = cameraStreamRef.current;
      stream?.getTracks().forEach((t) => t.stop());
      cameraStreamRef.current = null;
      setCameraOn(false);
      setCameraStream(null);
      cameraPermissionGrantedRef.current = false;
      setCameraPermissionGranted(false);
      cameraPreviewRef.current = null;
      void postVoiceCameraStatus(false, false).catch(() => undefined);
      void postVoiceCameraPermission(false).catch(() => undefined);
    }, CAMERA_IDLE_MS);
  }, [cameraOn]);

  const releaseCameraStream = useCallback(() => {
    clientRef.current?.detachCameraStream();
    const stream = cameraStreamRef.current;
    stream?.getTracks().forEach((t) => t.stop());
    cameraStreamRef.current = null;
    setCameraStream(null);
    setCameraOn(false);
    cameraPermissionGrantedRef.current = false;
    setCameraPermissionGranted(false);
    cameraPreviewRef.current = null;
    void postVoiceCameraStatus(false, false).catch(() => undefined);
    void postVoiceCameraPermission(false).catch(() => undefined);
  }, []);

  const announceCameraPrivacy = useCallback(
    (speak = true) => {
      setStatusLabel("Cámara activa — vista en vivo");
      setErrorMessage(null);
      callbacks?.onTranscript?.(CAMERA_PRIVACY_SPOKEN, "model", {
        partial: false,
      });
      if (speak) {
        clientRef.current?.sendNarrationBrief(CAMERA_PRIVACY_SPOKEN);
      }
    },
    [callbacks],
  );

  const stopSession = useCallback(async () => {
    userInitiatedStopRef.current = true;
    voiceSessionGenRef.current += 1;
    lastPersistedAgentLineRef.current = "";
    clearUsageInterval();
    clientRef.current?.disconnect();
    clientRef.current = null;
    void retellClientRef.current?.stopCall();
    retellClientRef.current = null;
    setRetellPollActive(false);
    lastVoiceActionIdRef.current = null;
    isRetellSessionRef.current = false;
    setVoiceSessionActive(false);
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
    sessionMediaPreauthRef.current = null;
    cameraPermissionGrantedRef.current = false;
    setCameraPermissionGranted(false);
    setMicOn(false);
    setCameraOn(false);
    setRetellInputLevel(0);
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
    pendingPublishRef.current = null;
    lastPublishableImageRef.current = null;
    void postVoiceSessionEnd().catch(() => undefined);
    setPaused(false);
    setOrbState("idle");
    setStatusLabel(ORB_STATE_LABELS.idle);
    saveMicPreference(false);
    onUsageRefresh?.();
    retellEarlyEndRetriesRef.current = 0;
    retellCallStartedAtRef.current = 0;
  }, [clearUsageInterval, onUsageRefresh]);

  const toggleCameraRef = useRef<
    (force?: boolean, opts?: { announce?: boolean }) => Promise<void>
  >(async () => undefined);

  const primeSessionMediaFromGesture = useCallback((): Promise<void> => {
    if (sessionMediaPreauthRef.current) {
      return sessionMediaPreauthRef.current;
    }
    if (!navigator.mediaDevices?.getUserMedia || isRetellVoice()) {
      return Promise.resolve();
    }

    const task = (async () => {
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
      } catch {
        /* El micrófono se vuelve a solicitar en toggleMic si falla aquí. */
      }
    })();

    sessionMediaPreauthRef.current = task;
    return task;
  }, []);

  const startCameraWithFacing = useCallback(
    async (facing: "user" | "environment") => {
      cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
      const stream = await requestCameraMediaStream({
        facingMode: { ideal: facing },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { ideal: 24, max: 30 },
      });
      cameraFacingRef.current = facing;
      setCameraFacing(facing);
      cameraStreamRef.current = stream;
      setCameraStream(stream);
      cameraPermissionGrantedRef.current = true;
      setCameraPermissionGranted(true);
      setCameraOn(true);
      resetCameraIdleTimer();
      void postVoiceCameraPermission(true).catch(() => undefined);
      void postVoiceCameraStatus(true, true).catch(() => undefined);
      void clientRef.current?.attachCameraStream(stream);
      return stream;
    },
    [resetCameraIdleTimer],
  );

  const applyCameraStreamFromVoice = useCallback(
    (stream: MediaStream) => {
      cameraStreamRef.current = stream;
      setCameraStream(stream);
      setCameraOn(true);
      resetCameraIdleTimer();
      void clientRef.current?.attachCameraStream(stream);
      void postVoiceCameraStatus(true, true).catch(() => undefined);
      bindHudCameraFeed(stream);
      setStatusLabel("Cámara activa — vista en vivo");
      setErrorMessage(null);
    },
    [resetCameraIdleTimer],
  );

  const toggleCamera = useCallback(
    async (
      force?: boolean,
      opts?: { announce?: boolean },
    ) => {
      const next = force ?? !cameraOn;
      if (!next) {
        releaseCameraStream();
        return;
      }

      const stream = cameraStreamRef.current;
      const streamLive =
        !!stream?.active &&
        stream.getVideoTracks().some((t) => t.readyState === "live" && t.enabled);
      if (streamLive) {
        applyCameraStreamFromVoice(stream);
        if (opts?.announce !== false) {
          announceCameraPrivacy(false);
        }
        return;
      }
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
        cameraStreamRef.current = null;
        setCameraStream(null);
      }
      try {
        await startCameraWithFacing(cameraFacingRef.current);
        bindHudCameraFeed(cameraStreamRef.current!);
        if (opts?.announce !== false) {
          announceCameraPrivacy(true);
        }
      } catch {
        setErrorMessage(CAMERA_PERMISSION_DENIED_SPOKEN);
        callbacks?.onTranscript?.(CAMERA_PERMISSION_DENIED_SPOKEN, "model", {
          partial: false,
        });
        clientRef.current?.sendNarrationBrief(CAMERA_PERMISSION_DENIED_SPOKEN);
        void postVoiceCameraPermission(false).catch(() => undefined);
      }
    },
    [
      cameraOn,
      applyCameraStreamFromVoice,
      releaseCameraStream,
      startCameraWithFacing,
      announceCameraPrivacy,
      callbacks,
    ],
  );
  toggleCameraRef.current = toggleCamera;

  const activateCameraFromVoice = useCallback(
    (opts?: { ackActionId?: number; showFeedback?: boolean }) => {
      const finish = (promise: Promise<void>) => {
        if (cameraActivateInFlightRef.current === promise) {
          cameraActivateInFlightRef.current = null;
        }
        return promise;
      };

      const stream = cameraStreamRef.current;
      const streamLive =
        !!stream?.active &&
        stream.getVideoTracks().some((t) => t.readyState === "live" && t.enabled);
      if (streamLive) {
        applyCameraStreamFromVoice(stream);
        if (opts?.showFeedback !== false) {
          announceCameraPrivacy(false);
        }
        if (opts?.ackActionId) {
          return finish(ackVoiceClientAction(opts.ackActionId));
        }
        return Promise.resolve();
      }

      if (cameraActivateInFlightRef.current) {
        return cameraActivateInFlightRef.current.then(() => {
          if (opts?.ackActionId) {
            return ackVoiceClientAction(opts.ackActionId);
          }
          return undefined;
        });
      }

      const task = (async () => {
        try {
          await startCameraWithFacing(cameraFacingRef.current);
          bindHudCameraFeed(cameraStreamRef.current!);
          if (opts?.showFeedback !== false) {
            announceCameraPrivacy(true);
          }
        } catch (error) {
          console.error("[CAMERA] activate error:", error);
          setErrorMessage(CAMERA_PERMISSION_DENIED_SPOKEN);
          callbacks?.onTranscript?.(CAMERA_PERMISSION_DENIED_SPOKEN, "model", {
            partial: false,
          });
          clientRef.current?.sendNarrationBrief(CAMERA_PERMISSION_DENIED_SPOKEN);
          void postVoiceCameraPermission(false).catch(() => undefined);
          void postVoiceCameraStatus(false, false).catch(() => undefined);
        }
        if (opts?.ackActionId) {
          await ackVoiceClientAction(opts.ackActionId);
        }
      })();

      cameraActivateInFlightRef.current = task;
      return finish(task);
    },
    [
      applyCameraStreamFromVoice,
      startCameraWithFacing,
      announceCameraPrivacy,
      callbacks,
    ],
  );
  activateCameraFromVoiceRef.current = activateCameraFromVoice;

  const flipCamera = useCallback(async () => {
    if (!cameraOn) return;
    const nextFacing: "user" | "environment" =
      cameraFacingRef.current === "user" ? "environment" : "user";
    try {
      clientRef.current?.detachCameraStream();
      await startCameraWithFacing(nextFacing);
      setStatusLabel(
        nextFacing === "environment"
          ? "Cámara trasera activa"
          : "Cámara frontal activa",
      );
    } catch {
      setErrorMessage("No pude cambiar de cámara. Intenta de nuevo.");
    }
  }, [cameraOn, startCameraWithFacing]);

  const toggleMic = useCallback(async () => {
    if (micBusyRef.current) return;
    if (micOn) {
      await stopSession();
      return;
    }

    unlockVoiceAudioOnGesture();
    const preauth = primeSessionMediaFromGesture();

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

    micBusyRef.current = true;
    setMicBusy(true);
    setErrorMessage(null);
    setOrbState("processing");
    setStatusLabel("Activando micrófono…");

    const sessionGen = voiceSessionGenRef.current + 1;
    voiceSessionGenRef.current = sessionGen;
    userInitiatedStopRef.current = false;
    retellEarlyEndRetriesRef.current = 0;
    retellCallStartedAtRef.current = 0;
    const isStale = () => voiceSessionGenRef.current !== sessionGen;

    try {
      await preauth;

      if (!isRetellVoice() && !micStreamRef.current) {
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
      }

      setMicOn(true);
      saveMicPreference(true);

      setStatusLabel(isRetellVoice() ? "Conectando con CED…" : ORB_STATE_LABELS.processing);

      const [voiceSession] = await Promise.all([
        startVoiceSession(),
        isRetellVoice() ? warmupRetellVoiceApi() : Promise.resolve(),
      ]);
      usageSessionRef.current = voiceSession.session_id;
      conversationRef.current = voiceSession.conversation_id;
      onUsageRefresh?.();

      if (isRetellVoice()) {
        isRetellSessionRef.current = true;
        setVoiceSessionActive(true);
        setStatusLabel("Iniciando llamada…");
        const registration = await registerRetellCall();
        if (isStale()) return;
        if (!registration.ok) {
          setErrorMessage(registration.error || "No pude iniciar voz Retell.");
          setOrbState("error");
          await stopSession();
          return;
        }

        const retell = new CedRetellClient();
        retellClientRef.current = retell;
        retell.setCallbacks({
          onCallStarted: () => {
            if (isStale()) return;
            retellCallStartedAtRef.current = Date.now();
            lastPublishableImageRef.current = null;
            setRetellPollActive(true);
            lastVoiceActionIdRef.current = null;
            lastToolEventIdRef.current = 0;
            setOrbState("listening");
            setStatusLabel(ORB_STATE_LABELS.listening);
          },
          onCallEnded: () => {
            if (isStale()) return;
            const elapsed =
              retellCallStartedAtRef.current > 0
                ? Date.now() - retellCallStartedAtRef.current
                : 0;
            const client = retellClientRef.current;
            if (
              !userInitiatedStopRef.current &&
              client &&
              elapsed > 0 &&
              elapsed < 12_000 &&
              retellEarlyEndRetriesRef.current < 1
            ) {
              retellEarlyEndRetriesRef.current += 1;
              console.warn(
                "[CED:RETELL] call_ended prematuro (%sms) — reintento único",
                elapsed,
              );
              void (async () => {
                try {
                  const registration = await registerRetellCall();
                  if (isStale() || !registration.ok) {
                    setRetellPollActive(false);
                    await stopSession();
                    return;
                  }
                  retellCallStartedAtRef.current = Date.now();
                  await client.startCall(
                    registration.access_token,
                    registration.call_id,
                  );
                  client.setMuted(mutedRef.current);
                  setOrbState("listening");
                  setStatusLabel(ORB_STATE_LABELS.listening);
                } catch {
                  setRetellPollActive(false);
                  await stopSession();
                }
              })();
              return;
            }
            setRetellPollActive(false);
            void stopSession();
          },
          onAgentTalking: (talking) => {
            if (isStale()) return;
            modelSpeakingRef.current = talking;
            setOrbState(talking ? "speaking" : "listening");
            setStatusLabel(
              talking ? ORB_STATE_LABELS.speaking : ORB_STATE_LABELS.listening,
            );
          },
          onTranscript: (text, role, options) => {
            if (isStale()) return;
            callbacks?.onTranscript?.(
              text,
              role === "user" ? "user" : "model",
              options,
            );
            if (role === "user") {
              setHeardIndicator({
                status: "heard",
                userText: text,
                heardAt: Date.now(),
              });
              if (cameraStreamRef.current?.active) {
                void postVoiceCameraStatus(true, true).catch(() => undefined);
              }
              const camIntent = parseCameraIntent(text);
              if (camIntent === "activate") {
                void toggleCameraRef.current(true);
              }
            } else {
              modelRepliedTurnRef.current = true;
              const cleaned = text.trim();
              if (cleaned.length >= 40) {
                recentAssistantTextsRef.current = [
                  ...recentAssistantTextsRef.current.slice(-4),
                  cleaned,
                ];
              }
            }
            persistVoiceTranscript(
              role === "user" ? "user" : "model",
              text,
              options,
            );
          },
          onClearAgentPartial: () => {
            callbacks?.onClearAgentPartial?.();
          },
          onError: (message) => {
            if (isStale()) return;
            setErrorMessage(message);
            setOrbState("error");
          },
          onAudioLevel: (level) => {
            if (isStale()) return;
            setRetellInputLevel(level);
          },
        });

        usageIntervalRef.current = setInterval(() => {
          const sid = usageSessionRef.current;
          if (!sid) return;
          void (async () => {
            try {
              const result = await tickVoiceSessionDetailed(
                sid,
                USAGE_TICK_SECONDS,
              );
              if (!result.ok) {
                if (result.authError) {
                  console.warn(
                    "[CED] usage/tick sin auth — la voz sigue activa",
                  );
                }
                return;
              }
              const data = result.data;
              onUsageRefresh?.();
              if (data.blocked || data.should_disconnect) {
                setErrorMessage(
                  "Has alcanzado tu límite diario de voz. Recarga o continúa mañana.",
                );
                await stopSession();
              } else if (data.access_denied) {
                setErrorMessage(
                  "Tu suscripción no está activa. Renueva en Precios para usar la voz.",
                );
                await stopSession();
              }
            } catch {
              /* ignore — no cerrar voz por fallo de red */
            }
          })();
        }, USAGE_TICK_SECONDS * 1000);

        await retell.startCall(registration.access_token, registration.call_id);
        if (isStale()) return;
        retell.setMuted(mutedRef.current);
        setOrbState("listening");
        setStatusLabel(ORB_STATE_LABELS.listening);
        return;
      }

      const client = new CedLiveClient();
      clientRef.current = client;
      client.setRemoteMuted(mutedRef.current);
      client.setMicTrackEnabled(false);

      usageIntervalRef.current = setInterval(() => {
        const sid = usageSessionRef.current;
        if (!sid) return;
        void (async () => {
          try {
            const result = await tickVoiceSessionDetailed(
              sid,
              USAGE_TICK_SECONDS,
            );
            if (!result.ok) {
              if (result.authError) {
                console.warn("[CED] usage/tick sin auth — la voz sigue activa");
              }
              return;
            }
            const data = result.data;
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
            /* ignore — no cerrar voz por fallo de red */
          }
        })();
      }, USAGE_TICK_SECONDS * 1000);

      const micActiveRef = { current: true };
      const greetingSentRef = { current: false };
      const greetingPendingRef = { current: false };
      const idlePresenceSentRef = { current: false };
      const idlePresenceTimerRef = { current: null as number | null };
      const lastUserSpeechAtRef = { current: 0 };
      const setupTimerRef = { current: null as number | null };
      const responseWatchdogRef = { current: null as number | null };
      const micUnmuteTimerRef = { current: null as number | null };
      const lastResponseStartRef = { current: 0 };
      const socialCommentsHandledAtRef = { current: 0 };
      const prospectionInFlightRef = { current: false };

      const finishClientVoiceAction = () => {
        client.releaseTurnAfterClientAction();
        client.flushInputAudioBuffer();
        if (!isStale() && !pausedRef.current) {
          scheduleMicUnmute(700);
        }
      };

      const runProspectionActivate = () => {
        if (prospectionInFlightRef.current) return;
        prospectionInFlightRef.current = true;
        void (async () => {
          try {
            client.setMicTrackEnabled(false);
            const h = cedResolveHonorific(client.getUserAddress());
            await client.speakExactNarrationAsync(`Un momento, ${h}.`);
            if (isStale()) return;
            setStatusLabel("Activando prospección…");
            setOrbState("processing");
            const r = await Promise.race([
              enableProspection(),
              new Promise<{ ok: false; error: string }>((resolve) =>
                window.setTimeout(
                  () => resolve({ ok: false, error: "La activación tardó demasiado." }),
                  18_000,
                ),
              ),
            ]);
            if (isStale()) return;
            await client.speakExactNarrationAsync(
              r.ok
                ? `Prospección activada, ${h}.`
                : `No pude activar prospección, ${h}.`,
            );
          } catch {
            if (!isStale()) {
              const h = cedResolveHonorific(client.getUserAddress());
              await client.speakExactNarrationAsync(
                `No pude activar prospección, ${h}.`,
              );
            }
          } finally {
            prospectionInFlightRef.current = false;
            finishClientVoiceAction();
            if (!isStale() && !pausedRef.current) {
              scheduleMicUnmute(1200);
            }
          }
        })();
      };

      const clearMicUnmuteTimer = () => {
        if (micUnmuteTimerRef.current) {
          clearTimeout(micUnmuteTimerRef.current);
          micUnmuteTimerRef.current = null;
        }
      };

      const clearIdlePresenceTimer = () => {
        if (idlePresenceTimerRef.current) {
          clearTimeout(idlePresenceTimerRef.current);
          idlePresenceTimerRef.current = null;
        }
      };

      const scheduleIdlePresence = () => {
        /* Desactivado: hablaba solo tras silencio y confundía con TV/eco. */
      };

      /** Evita que el mic capte eco de Cedar mientras aún suena por WebRTC. */
      const scheduleMicUnmute = (delayMs = MIC_UNMUTE_AFTER_SPEECH_MS) => {
        clearMicUnmuteTimer();
        micUnmuteTimerRef.current = window.setTimeout(() => {
          micUnmuteTimerRef.current = null;
          if (isStale() || pausedRef.current) return;
          if (modelSpeakingRef.current || client.isResponseActive()) return;
          client.setMicTrackEnabled(true);
          enableListeningUi();
        }, delayMs);
      };

      const clearResponseWatchdog = () => {
        if (responseWatchdogRef.current) {
          clearTimeout(responseWatchdogRef.current);
          responseWatchdogRef.current = null;
        }
      };

      const releaseStuckConversation = (reason: string) => {
        cedVoiceLog(4, "Watchdog conversación", { reason });
        clearResponseWatchdog();
        clearMicUnmuteTimer();
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

      const enableListeningUi = (force = false) => {
        if (isStale() || !micActiveRef.current) return;
        setHeardIndicator({ status: "listening", userText: null, heardAt: null });
        if (
          force ||
          (!webFetchRef.current && !modelSpeakingRef.current && !clientWebSearchRef.current)
        ) {
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

      const notifyGeneratedImage = (url: string, prompt?: string) => {
        const normalized = normalizeCedMediaUrl(url);
        lastPublishableImageRef.current = normalized;
        callbacks?.onGeneratedImage?.(normalized, prompt);
      };

      const publishSuccessBrief = (platform: PublishPlatform) =>
        cedPublishSuccessPhrase(platform, client.getUserAddress());
      const publishFailureBrief = (reason: string) =>
        cedPublishFailurePhrase(reason, client.getUserAddress());

      const runSocialPublish = (
        platform: PublishPlatform,
        postText: string,
        userText: string,
      ) => {
        const body = postText.trim();
        if (!body || webFetchRef.current) return;
        webFetchRef.current = true;
        pendingPublishRef.current = null;
        setOrbState("processing");
        setStatusLabel(
          platform === "facebook"
            ? "Publicando en Facebook…"
            : "Publicando en Instagram…",
        );
        void (async () => {
          try {
            const image = await resolvePublishImage({}, userText);
            if (platform === "facebook") {
              const r = await publishFacebook(body, image);
              if (isStale()) return;
              client.sendNarrationBrief(
                r.ok ? publishSuccessBrief("facebook") : publishFailureBrief(r.error),
              );
              return;
            }
            if (!image.imageUrl && !image.imageData) {
              pendingPublishRef.current = {
                platform: "instagram",
                awaiting: "develop",
              };
              client.sendNarrationBrief("Necesito una imagen para Instagram.");
              return;
            }
            const r = await publishInstagram(body, image);
            if (isStale()) return;
            client.sendNarrationBrief(
              r.ok ? publishSuccessBrief("instagram") : publishFailureBrief(r.error),
            );
          } finally {
            webFetchRef.current = false;
          }
        })();
      };

      const runAdvancedAnalysis = (prompt: string) => {
        const q = prompt.trim();
        if (!q || webFetchRef.current) return;
        webFetchRef.current = true;
        advancedConfirmPendingRef.current = false;
        advancedConfirmAskedRef.current = false;
        setOrbState("processing");
        setStatusLabel("Consultando sistema avanzado…");
        void (async () => {
          try {
            const r = await fetchDeepAnalysis(
              q,
              CED_VOICE_PROFILE_LOCK.advancedSystem.fetchTimeoutMs,
            );
            if (isStale()) return;
            client.sendNarrationBrief(
              r.ok ? r.result : r.error || "No pude completar el análisis.",
            );
          } catch {
            if (!isStale()) {
              client.sendNarrationBrief("Falló la consulta al sistema avanzado.");
            }
          } finally {
            webFetchRef.current = false;
            pendingAdvancedPromptRef.current = "";
          }
        })();
      };

      const runGenerateImage = (prompt: string) => {
        if (webFetchRef.current) return;
        webFetchRef.current = true;
        setOrbState("processing");
        setStatusLabel("Generando imagen…");
        void (async () => {
          try {
            const r = await fetchGenerateImage(prompt);
            if (isStale()) return;
            if (r.ok) {
              notifyGeneratedImage(r.url, prompt);
              client.sendNarrationBrief("Ahí está.");
            } else {
              client.sendNarrationBrief(r.error);
            }
          } finally {
            webFetchRef.current = false;
          }
        })();
      };

      const runGeneratePdf = (title: string, content: string, userRequest?: string) => {
        if (webFetchRef.current) return;
        webFetchRef.current = true;
        setOrbState("processing");
        setStatusLabel("Generando PDF…");
        void (async () => {
          try {
            const cid = conversationRef.current;
            const pdf = await generatePdf(title, content, cid, userRequest ?? content);
            if (isStale()) return;
            client.sendNarrationBrief(
              `Listo. PDF "${pdf.title}" generado y guardado en tu historial.`,
            );
          } catch (err) {
            if (!isStale()) {
              const msg =
                err instanceof Error ? err.message : "No pude generar el PDF.";
              client.sendNarrationBrief(msg);
            }
          } finally {
            webFetchRef.current = false;
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
        if (webFetchRef.current || isStale()) return;
        webFetchRef.current = true;
        setOrbState("processing");
        setStatusLabel("Buscando en internet…");
        void (async () => {
          try {
            const hadStream = !!cameraStreamRef.current;
            if (!hadStream) {
              await toggleCameraRef.current(true);
            }
            const frame = await waitForCameraFrame(
              hadStream ? CAMERA_FRAME_READY_MS : CAMERA_FRAME_WARM_MS,
            );
            if (!frame) {
              client.sendNarrationBrief(
                "active la cámara primero para buscar lo que veo.",
              );
              return;
            }
            cedVoiceLog(5, "Visual web search", { q: question.slice(0, 60) });
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

      const runCameraAnalyze = (text: string) => {
        if (webFetchRef.current) return;
        webFetchRef.current = true;
        setOrbState("processing");
        setStatusLabel("Analizando cámara…");
        void (async () => {
          try {
            const hadStream = !!cameraStreamRef.current;
            if (!hadStream) {
              await toggleCameraRef.current(true);
            }
            const frame = await waitForCameraFrame(
              hadStream ? CAMERA_FRAME_READY_MS : CAMERA_FRAME_WARM_MS,
              true,
            );
            if (!frame) {
              client.sendNarrationBrief(
                "activa la cámara y muéstrame qué quieres que identifique.",
              );
              return;
            }
            lastPublishableImageRef.current = frame;
            const question = cameraAnalyzeQuestion(text);
            const result = await fetchVisionAnalyze(frame, question);
            if (result.ok) {
              client.sendNarrationBrief(result.summary);
            } else {
              client.sendNarrationBrief(`no pude analizar la cámara: ${result.error}`);
            }
          } catch {
            client.sendNarrationBrief("falló el análisis de cámara. Inténtalo de nuevo.");
          } finally {
            webFetchRef.current = false;
          }
        })();
      };

      const handleCameraActivate = (text: string) => {
        void (async () => {
          const hadStream = !!cameraStreamRef.current?.active;
          if (!hadStream) {
            await toggleCameraRef.current(true, { announce: false });
          }
          if (isCameraAnalyzeIntent(text)) {
            runCameraAnalyze(text);
            return;
          }
          if (isVisualSearchIntent(text)) {
            if (!hadStream) {
              await new Promise((r) => window.setTimeout(r, 500));
            }
            runVisualSearch(text);
            return;
          }
          client.sendNarrationBrief(CAMERA_PRIVACY_SPOKEN);
        })();
      };

      const markPublishFlow = (
        platform: PublishPlatform,
        draftText?: string,
      ) => {
        pendingPublishRef.current = {
          platform,
          awaiting: draftText ? "confirm" : "develop",
          draftText,
        };
      };

      const handleClientVoiceIntents = (text: string) => {
        const t = text.trim();
        if (!t) return;

        const pending = pendingPublishRef.current;

        if (pending && isPublishGoCommand(t)) {
          const { platform, draftText } = pending;
          pendingPublishRef.current = null;
          if (draftText?.trim()) {
            runSocialPublish(platform, draftText, t);
          } else {
            client.sendPublishConfirm(platform);
          }
          return;
        }

        const directPublish = parseDirectPublishContent(t);
        if (directPublish) {
          if (isPublishDirectCommand(t) || isPublishGoCommand(t)) {
            runSocialPublish(directPublish.platform, directPublish.content, t);
            return;
          }
          markPublishFlow(directPublish.platform, directPublish.content);
          return;
        }

        const planning = parsePublishIdea(t);
        if (planning) {
          markPublishFlow(planning.platform ?? detectPublishPlatform(t) ?? "facebook");
          return;
        }

        if (isPublishPlanningIntent(t)) {
          markPublishFlow(detectPublishPlatform(t) ?? "facebook");
          return;
        }

        const platformOnly = isPublishRequestWithoutContent(t);
        if (platformOnly) {
          markPublishFlow(platformOnly);
          return;
        }

        const fbMessage = parseFacebookPublishMessage(t);
        if (fbMessage) {
          if (isPublishDirectCommand(t) || isPublishGoCommand(t)) {
            runSocialPublish("facebook", fbMessage, t);
            return;
          }
          markPublishFlow("facebook", fbMessage);
          return;
        }

        const igRequest = parseInstagramPublishRequest(t);
        if (igRequest?.caption) {
          if (isPublishDirectCommand(t) || isPublishGoCommand(t)) {
            setOrbState("processing");
            setStatusLabel("Publicando en Instagram…");
            void (async () => {
              if (webFetchRef.current) return;
              webFetchRef.current = true;
              pendingPublishRef.current = null;
              try {
                const image =
                  igRequest.imageUrl != null
                    ? { imageUrl: igRequest.imageUrl }
                    : await resolvePublishImage({}, t);
                if (!image.imageUrl && !image.imageData) {
                  markPublishFlow("instagram");
                  client.sendNarrationBrief("Necesito una imagen para Instagram.");
                  return;
                }
                const r = await publishInstagram(igRequest.caption, image);
                if (isStale()) return;
                client.sendNarrationBrief(
                  r.ok
                    ? publishSuccessBrief("instagram")
                    : publishFailureBrief(r.error),
                );
              } finally {
                webFetchRef.current = false;
              }
            })();
            return;
          }
          markPublishFlow("instagram", igRequest.caption);
          return;
        }

        const imagePrompt = parseGenerateImagePrompt(t);
        if (imagePrompt && isGenerateImageIntent(t)) {
          runGenerateImage(imagePrompt);
          return;
        }

        const pdfRequest = parsePdfRequest(t, recentAssistantTextsRef.current);
        if (pdfRequest && isPdfIntent(t)) {
          runGeneratePdf(pdfRequest.title, pdfRequest.content, t);
          return;
        }

        if (isAddressPreferenceIntent(t)) {
          const addressPref = parseAddressPreference(t);
          const genderPref = parseGenderPreference(t);
          void (async () => {
            const updated = await updateUserAddress({
              ...(addressPref ? { preferredAddress: addressPref } : {}),
              ...(genderPref ? { gender: genderPref } : {}),
            });
            if (isStale()) return;
            if (updated) {
              client.setUserAddress(updated);
              clearEphemeralTokenCache();
            }
          })();
          return;
        }

        const camIntent = parseCameraIntent(t);
        if (camIntent === "activate") {
          handleCameraActivate(t);
          return;
        }
        if (camIntent === "deactivate") {
          void toggleCameraRef.current(false);
          return;
        }

        if (isCameraAnalyzeIntent(t)) {
          runCameraAnalyze(t);
          return;
        }

        if (isVisualSearchIntent(t)) {
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
            greetingPendingRef.current = true;
            client.setMicTrackEnabled(false);
            setStatusLabel("CED te saluda…");
            client.sendSessionGreeting();
          }
        },
        onGreetingComplete: () => {
          if (isStale()) return;
          greetingPendingRef.current = false;
          clearResponseWatchdog();
          modelSpeakingRef.current = false;
          client.flushInputAudioBuffer();
          clearMicUnmuteTimer();
          setOrbState("processing");
          setStatusLabel("Preparando escucha…");
          micUnmuteTimerRef.current = window.setTimeout(() => {
            micUnmuteTimerRef.current = null;
            if (isStale() || pausedRef.current) return;
            client.enableListeningAfterGreeting();
            client.setMicTrackEnabled(true);
            enableListeningUi(true);
          }, 2800);
        },
        onTranscriptUpdate: (text, role) => {
          if (isStale() || role !== "user") return;
          const trimmed = text.trim();
          if (!trimmed || /^<noise>$/i.test(trimmed)) return;
          lastUserSpeechAtRef.current = Date.now();
          idlePresenceSentRef.current = false;
          clearIdlePresenceTimer();
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
          const trimmed = text.trim();
          if (!trimmed) return;
          if (role === "model" && client.isRogueModelOutput(trimmed)) {
            return;
          }
          callbacks?.onTranscript?.(trimmed, role);
          persistVoiceTranscript(role, trimmed);
          if (role === "user") {
            if (client.isGreetingInProgress()) {
              return;
            }
            modelRepliedTurnRef.current = false;
            lastUserUtteranceRef.current = trimmed;

            // Comentarios / prospección ANTES que tratamiento
            if (isStandaloneHonorificPreference(trimmed)) {
              void (async () => {
                const pref = /^se[nñ]ora/i.test(trimmed) ? "Señora" : "Señor";
                const updated = await updateUserAddress({
                  preferredAddress: pref,
                  gender: pref === "Señora" ? "female" : "male",
                });
                if (isStale()) return;
                if (updated) {
                  client.setUserAddress(updated);
                  clearEphemeralTokenCache();
                }
              })();
              return;
            }

            if (client.isToolsEnabled()) {
              if (userExplicitlyRequestedProspection(trimmed)) {
                runProspectionActivate();
                return;
              }
              if (isAddressPreferenceIntent(trimmed)) {
                const addressPref = parseAddressPreference(trimmed);
                const genderPref = parseGenderPreference(trimmed);
                void (async () => {
                  const updated = await updateUserAddress({
                    ...(addressPref ? { preferredAddress: addressPref } : {}),
                    ...(genderPref ? { gender: genderPref } : {}),
                  });
                  if (isStale()) return;
                  if (updated) {
                    client.setUserAddress(updated);
                    clearEphemeralTokenCache();
                  }
                })();
                return;
              }
              return;
            }

            const addressPref = parseAddressPreference(trimmed);
            const genderPref = parseGenderPreference(trimmed);
            if (addressPref || genderPref) {
              void (async () => {
                const updated = await updateUserAddress({
                  ...(addressPref ? { preferredAddress: addressPref } : {}),
                  ...(genderPref ? { gender: genderPref } : {}),
                });
                if (isStale()) return;
                if (updated) {
                  client.setUserAddress(updated);
                  clearEphemeralTokenCache();
                }
              })();
              return;
            }

            if (userExplicitlyRequestedProspection(trimmed)) {
              runProspectionActivate();
              return;
            }

            if (isAdvancedConfirmAnswer(trimmed) && advancedConfirmPendingRef.current) {
              const q =
                pendingAdvancedPromptRef.current.trim() ||
                lastUserUtteranceRef.current.trim();
              if (q) {
                runAdvancedAnalysis(q);
                return;
              }
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
            } else if (
              isGenerateImageIntent(text) ||
              isSocialPublishIntent(text) ||
              isPublishGoCommand(text)
            ) {
              handleClientVoiceIntents(text.trim());
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
        onProspectionIntent: () => {
          if (isStale()) return;
          runProspectionActivate();
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
            consultar_cerebro_interno: "Consultando cerebro interno…",
            [CONSULTAR_SISTEMA_AVANZADO]: "Consultando sistema avanzado…",
            [GUARDAR_MEMORIA]: "Guardando en memoria…",
            [BUSCAR_MEMORIA]: "Consultando memoria…",
            [ACTIVAR_PROSPECCION]: "Activando prospección…",
            [DESACTIVAR_PROSPECCION]: "Desactivando prospección…",
            [REPORTE_PROSPECCION]: "Generando reporte…",
            [PUBLICAR_FACEBOOK]: "Publicando en Facebook…",
            [PUBLICAR_INSTAGRAM]: "Publicando en Instagram…",
            [LEER_COMENTARIOS_REDES]: "Leyendo comentarios…",
            [BUSCAR_LO_VISIBLE]: "Buscando lo que veo…",
            [ANALIZAR_CAMARA]: "Analizando cámara…",
            request_camera_activation: "Activando cámara…",
            request_camera_deactivation: "Apagando cámara…",
            generate_image: "Generando imagen con IA…",
            generate_image_with_reference: "Generando variación con referencia…",
            [GENERAR_PDF]: "Generando PDF…",
          };
          setStatusLabel(labels[toolName] ?? "Consultando…");
          scheduleResponseWatchdog();
        },
        onGeneratedImage: (url, prompt) => {
          notifyGeneratedImage(url, prompt);
        },
        onGenerateImageWithReference: async (args) => {
          const prompt = String(args.prompt ?? "").trim() || "Genera una variación de la referencia";
          const styleModeRaw = String(args.style_mode ?? "variation");
          const styleMode =
            styleModeRaw === "inspired" || styleModeRaw === "edit"
              ? styleModeRaw
              : "variation";
          const quality = String(args.quality ?? "standard") === "hd" ? "hd" : "standard";

          const resolved = await resolvePublishImage(
            { from_camera: true, use_last_image: true },
            lastUserUtteranceRef.current,
          );
          const blob = await publishImageToBlob(resolved);
          if (!blob) {
            return {
              ok: false,
              error:
                "No tengo imagen de referencia. Muéstrame algo con la cámara o genera una imagen primero.",
            };
          }

          const result = await fetchGenerateImageWithReference(
            prompt,
            blob,
            styleMode,
            quality,
          );
          if (result.ok) {
            return {
              ok: true,
              url: result.url,
              spoken: "Ahí está.",
            };
          }
          return { ok: false, error: result.error || "No pude generar con la referencia." };
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
            if (r.ok && /^(tratamiento|como_llamarme|preferred_address|titulo)$/i.test(key)) {
              const synced = await updateUserAddress({ preferredAddress: content });
              if (synced) {
                client.setUserAddress(synced);
                clearEphemeralTokenCache();
              }
            }
            return {
              spoken: r.ok
                ? /^(tratamiento|como_llamarme)$/i.test(key)
                  ? `Entendido, ${cedResolveHonorific(client.getUserAddress())}.`
                  : "guardado en memoria cognitiva."
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
          if (name === RECALL_PREVIOUS_CONVERSATIONS) {
            const q = String(args.query ?? args.consulta ?? "").trim();
            const days = Number(args.days_back ?? 30) || 30;
            const r = await recallPreviousConversations(q, days);
            return {
              spoken: r.ok
                ? r.spoken || "encontré contexto previo."
                : r.error || "no encontré conversaciones anteriores.",
            };
          }
          if (name === SAVE_LONG_TERM_MEMORY) {
            const category = String(args.category ?? "fact").trim();
            const key = String(args.key ?? args.clave ?? "nota").trim();
            const value = String(args.value ?? args.contenido ?? "").trim();
            const importance = Number(args.importance ?? 5) || 5;
            if (!value) {
              return { spoken: "no recibí qué guardar." };
            }
            const r = await saveLongTermMemory(category, key, value, importance);
            return {
              spoken: r.ok ? "entendido." : r.error || "no pude guardar eso.",
            };
          }
          if (name === ACTIVAR_PROSPECCION) {
            const r = await enableProspection();
            const h = cedResolveHonorific(client.getUserAddress());
            return {
              spoken: r.ok
                ? `Prospección activada, ${h}.`
                : `No pude activar prospección, ${h}.`,
            };
          }
          if (name === DESACTIVAR_PROSPECCION) {
            const r = await disableProspection();
            const h = cedResolveHonorific(client.getUserAddress());
            return {
              spoken: r.ok
                ? `Prospección desactivada, ${h}.`
                : `No pude desactivar prospección, ${h}.`,
            };
          }
          if (name === REPORTE_PROSPECCION) {
            const r = await fetchProspectionReport();
            return {
              spoken: r.ok ? r.spoken : "no pude obtener el reporte.",
            };
          }
          if (name === LEER_COMENTARIOS_REDES) {
            if (Date.now() - socialCommentsHandledAtRef.current < 5_000) {
              return { spoken: "Ya consulté los comentarios.", ok: true };
            }
            socialCommentsHandledAtRef.current = Date.now();
            const platRaw = String(args.platform ?? "both").trim().toLowerCase();
            const platform =
              platRaw === "instagram" || platRaw === "ig"
                ? "instagram"
                : platRaw === "facebook" || platRaw === "fb"
                  ? "facebook"
                  : "both";
            const r = await fetchSocialComments(platform);
            return {
              spoken: r.ok ? r.spoken : r.error || "No pude leer los comentarios.",
              ok: r.ok,
            };
          }
          if (name === PUBLICAR_FACEBOOK) {
            const fromArgs = String(
              args.mensaje ?? args.message ?? args.texto ?? "",
            ).trim();
            const fromUtterance =
              parseFacebookPublishMessage(lastUserUtteranceRef.current) ??
              parseDirectPublishContent(lastUserUtteranceRef.current)?.content ??
              pendingPublishRef.current?.draftText ??
              "";
            const message = fromArgs || fromUtterance.trim();
            if (!message) {
              markPublishFlow("facebook");
              const h = cedResolveHonorific(client.getUserAddress());
              return {
                spoken: `Muy bien, ${h}. ¿Desea agregar algo más o que le sugiera una idea para la publicación?`,
              };
            }
            const image = await resolvePublishImage(
              args,
              lastUserUtteranceRef.current,
            );
            const r = await publishFacebook(message, image);
            pendingPublishRef.current = null;
            cedVoiceLog(6, "publicar_facebook", { ok: r.ok, error: r.ok ? undefined : r.error });
            return {
              spoken: r.ok
                ? cedPublishSuccessPhrase("facebook", client.getUserAddress())
                : cedPublishFailurePhrase(`${r.error}`, client.getUserAddress()),
              ok: r.ok,
            };
          }
          if (name === PUBLICAR_INSTAGRAM) {
            const caption = String(
              args.caption ?? args.mensaje ?? args.texto ?? "",
            ).trim();
            if (!caption) {
              markPublishFlow("instagram");
              const h = cedResolveHonorific(client.getUserAddress());
              return {
                spoken: `Muy bien, ${h}. ¿Desea agregar algo más o que le sugiera una idea para la publicación?`,
              };
            }
            const image = await resolvePublishImage(
              args,
              lastUserUtteranceRef.current,
            );
            if (!image.imageUrl && !image.imageData) {
              markPublishFlow("instagram");
              return {
                spoken: "Necesito una imagen para Instagram.",
              };
            }
            const r = await publishInstagram(caption, image);
            pendingPublishRef.current = null;
            cedVoiceLog(6, "publicar_instagram", { ok: r.ok, error: r.ok ? undefined : r.error });
            return {
              spoken: r.ok
                ? cedPublishSuccessPhrase("instagram", client.getUserAddress())
                : cedPublishFailurePhrase(`${r.error}`, client.getUserAddress()),
              ok: r.ok,
            };
          }
          if (name === BUSCAR_LO_VISIBLE) {
            const hadStream = !!cameraStreamRef.current;
            if (!hadStream) {
              await toggleCameraRef.current(true);
            }
            const frame = await waitForCameraFrame(
              hadStream ? CAMERA_FRAME_READY_MS : CAMERA_FRAME_WARM_MS,
            );
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
          if (name === ANALIZAR_CAMARA) {
            if (!client.userExplicitlyRequestedVision()) {
              return { spoken: "", ok: false };
            }
            const hadStream = !!cameraStreamRef.current;
            if (!hadStream) {
              await toggleCameraRef.current(true);
            }
            const frame = await waitForCameraFrame(
              hadStream ? CAMERA_FRAME_READY_MS : CAMERA_FRAME_WARM_MS,
              true,
            );
            if (!frame) {
              return {
                spoken: "no pude capturar la cámara. Actívala y vuelve a intentar.",
              };
            }
            const pregunta = String(
              args.pregunta ?? args.question ?? "¿Qué ves en la imagen?",
            ).trim();
            const result = await fetchVisionAnalyze(frame, pregunta);
            if (result.ok) {
              return { spoken: result.summary };
            }
            return { spoken: `no pude analizar la cámara: ${result.error}` };
          }
          if (name === GENERAR_PDF) {
            const title = String(args.titulo ?? args.title ?? "Documento CED").trim();
            let content = String(args.contenido ?? args.content ?? "").trim();
            if (!content) content = title;
            const userRequest = String(
              args._user_request ?? args.user_request ?? content ?? title,
            ).trim();
            const cid = conversationRef.current;
            try {
              const pdf = await generatePdf(title, content, cid, userRequest);
              return {
                spoken: `Listo. PDF "${pdf.title}" generado y guardado en tu historial.`,
              };
            } catch (err) {
              const msg =
                err instanceof Error ? err.message : "No pude generar el PDF.";
              return { spoken: msg };
            }
          }
          return { spoken: "herramienta no reconocida." };
        },
        onResponseStart: () => {
          if (isStale()) return;
          clearMicUnmuteTimer();
          lastResponseStartRef.current = Date.now();
          modelSpeakingRef.current = true;
          modelRepliedTurnRef.current = true;
          client.setMicTrackEnabled(false);
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
        onModelAudioDone: () => {
          if (isStale()) return;
          if (greetingPendingRef.current) {
            return;
          }
          scheduleMicUnmute(MIC_UNMUTE_AFTER_SPEECH_MS + 100);
        },
        onInterrupted: () => {
          cedVoiceLog(5, "OpenAI interrupted");
          clearResponseWatchdog();
          clearMicUnmuteTimer();
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
          if (greetingPendingRef.current) {
            setOrbState("processing");
            setStatusLabel("Preparando escucha…");
            return;
          }
          client.flushInputAudioBuffer();
          scheduleMicUnmute();
          if (micActiveRef.current && !greetingPendingRef.current) {
            scheduleIdlePresence();
          }
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
          if (intent === "activate" && !client.userExplicitlyRequestedVision?.()) return;
          void toggleCameraRef.current(intent === "activate");
        },
        onCameraTool: async (intent) => {
          if (intent === "activate" && !client.getLastMeaningfulUserUtterance().trim()) {
            return false;
          }
          if (intent === "activate") {
            if (!cameraStreamRef.current) {
              await toggleCameraRef.current(true);
            }
            const stream = cameraStreamRef.current;
            if (stream) {
              await client.attachCameraStream(stream);
            }
            return Boolean(stream);
          }
          client.detachCameraStream();
          await toggleCameraRef.current(false);
          return true;
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
                voicePace: prefsRef.current.voicePace,
                voiceWarmth: prefsRef.current.voiceWarmth,
                voiceEnergy: prefsRef.current.voiceEnergy,
                voiceProfile: prefsRef.current.voiceProfile,
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
      const stream = micStreamRef.current;
      if (!stream) {
        setErrorMessage("No se detectó flujo de micrófono.");
        setOrbState("error");
        await stopSession();
        return;
      }
      const ok = await client.connect(handlers, {
        voiceName: prefsRef.current.voiceName,
        language: prefsRef.current.language,
        responseSpeed: prefsRef.current.responseSpeed,
        voicePace: prefsRef.current.voicePace,
        voiceWarmth: prefsRef.current.voiceWarmth,
        voiceEnergy: prefsRef.current.voiceEnergy,
        voiceProfile: prefsRef.current.voiceProfile,
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
      micBusyRef.current = false;
      setMicBusy(false);
    }
  }, [
    micOn,
    micBusy,
    primeSessionMediaFromGesture,
    stopSession,
    persistMessage,
    onUsageRefresh,
    callbacks,
  ]);

  useEffect(() => {
    clientRef.current?.setRemoteMuted(muted);
    retellClientRef.current?.setMuted(muted);
  }, [muted]);

  useEffect(() => {
    if (!micOn) return;
    if (isRetellSessionRef.current) {
      retellClientRef.current?.setMuted(paused || mutedRef.current);
      return;
    }
    const client = clientRef.current;
    if (!client) return;
    client.setMicTrackEnabled(!paused);
    if (paused) {
      client.hardPause();
    } else if (!client.isGreetingInProgress()) {
      client.resumeListening();
    }
  }, [micOn, paused]);

  useEffect(() => {
    return () => {
      voiceSessionGenRef.current += 1;
      clientRef.current?.disconnect();
      void retellClientRef.current?.stopCall();
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

    void video.play().then(() => {
      if (cancelled) return;
      maybeSendFrame();
    });

    const frameTimer = window.setInterval(maybeSendFrame, VIDEO_SEND_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(frameTimer);
      video.srcObject = null;
      if (cameraCaptureVideoRef.current === video) {
        cameraCaptureVideoRef.current = null;
      }
    };
  }, [cameraOn, captureCameraJpeg, resetCameraIdleTimer]);

  const togglePause = useCallback(() => {
    setPaused((p) => {
      const next = !p;
      if (isRetellSessionRef.current) {
        retellClientRef.current?.setMuted(next || mutedRef.current);
      } else {
        clientRef.current?.setMicTrackEnabled(!next);
      }
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
        voicePace: prefsRef.current.voicePace,
        voiceWarmth: prefsRef.current.voiceWarmth,
        voiceEnergy: prefsRef.current.voiceEnergy,
        voiceProfile: prefsRef.current.voiceProfile,
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

  const registerChatImageForVoice = useCallback(
    async (preview: string, file?: File) => {
      if (!isRetellSessionRef.current) {
        throw new Error("Sesión de voz no activa.");
      }
      const normalized = preview.startsWith("http")
        ? normalizeCedMediaUrl(preview)
        : preview;
      lastPublishableImageRef.current = normalized;
      let imageData = normalized;
      if (file && !normalized.startsWith("data:")) {
        imageData = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });
      }
      const result = await postVoiceChatImage(
        imageData.startsWith("http")
          ? { image_url: imageData, filename: file?.name }
          : { image_data: imageData, filename: file?.name },
      );
      if (result.image_url) {
        lastPublishableImageRef.current = normalizeCedMediaUrl(result.image_url);
      }
      cedVoiceLog(5, "Chat image registered for voice publish", {
        via: imageData.startsWith("http") ? "url" : "data",
      });
      return result;
    },
    [],
  );

  return {
    orbState,
    statusLabel,
    audioLevel,
    micOn,
    cameraOn,
    cameraFacing,
    cameraPermissionGranted,
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
    primeSessionMediaFromGesture,
    toggleCamera,
    flipCamera,
    togglePause,
    setMuted,
    stopSession,
    updatePrefs,
    applyVoiceChange,
    clearError,
    registerChatImageForVoice,
    voiceSessionActive,
  };
}
