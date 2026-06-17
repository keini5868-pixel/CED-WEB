/**
 * Cliente OpenAI Realtime vía WebRTC (recomendado por OpenAI para navegadores).
 * Audio in/out por RTCPeerConnection; eventos y tools por data channel oai-events.
 */

import type { VoiceSessionPreferences } from "@ced/types";

import { fetchDeepAnalysis, fetchGenerateImage, fetchVoiceBrief, negotiateRealtimeCall } from "@/lib/api/openai";
import type { UserAddressContext } from "@/lib/api/profile";
import { fetchEphemeralTokenCached } from "@/lib/voice/ephemeralTokenCache";
import { parseCameraIntent } from "@/lib/voice/cameraIntents";
import { cedVoiceError, cedVoiceLog, cedRealtimeLog } from "@/lib/voice/cedVoiceLogger";
import {
  ANALIZAR_CAMARA,
  BUSCAR_MEMORIA,
  CONSULTAR_SISTEMA_AVANZADO,
  GENERAR_PDF,
  GUARDAR_MEMORIA,
  LIVE_TOOL_NAMES,
  PUBLICAR_FACEBOOK,
  PUBLICAR_INSTAGRAM,
  RECALL_PREVIOUS_CONVERSATIONS,
  SAVE_LONG_TERM_MEMORY,
} from "@/lib/voice/liveTools";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import { isBenignRealtimeError } from "@/lib/voice/realtimeErrors";
import {
  isInputTranscriptionCompleted,
  isResponseAudioDone,
  isResponseAudioTranscriptDelta,
} from "@/lib/voice/realtimeEvents";
import { voiceTelemetry } from "@/lib/voice/voiceTelemetry";
import {
  cedBriefTurn,
  cedPublishConfirmTurn,
  cedPublishFailurePhrase,
  cedPublishSuccessPhrase,
  cedReceptionGreetingPhrase,
  cedAdvancedBriefTurn,
  CED_ADVANCED_CONFIRM_PHRASE,
} from "@/lib/voice/live/ced-brief-messages";

const TOOL_ALIAS: Record<string, string> = {
  save_memory: GUARDAR_MEMORIA,
  recall_memory: BUSCAR_MEMORIA,
  recall_previous_conversations: RECALL_PREVIOUS_CONVERSATIONS,
  save_to_long_term_memory: SAVE_LONG_TERM_MEMORY,
  generar_pdf: GENERAR_PDF,
  consultar_claude: CONSULTAR_SISTEMA_AVANZADO,
  analyze_camera_frame: ANALIZAR_CAMARA,
  publish_to_social: "publicar_facebook",
};

function normalizeToolInvocation(
  rawName: string,
  args: Record<string, unknown>,
): { name: string; args: Record<string, unknown> } {
  if (rawName === "publish_to_social") {
    const platform = String(args.platform ?? "facebook").toLowerCase();
    const content = String(
      args.content ?? args.message ?? args.mensaje ?? args.texto ?? "",
    ).trim();
    if (platform === "instagram") {
      return {
        name: "publicar_instagram",
        args: { ...args, caption: content || args.caption },
      };
    }
    return {
      name: "publicar_facebook",
      args: { ...args, mensaje: content || args.mensaje },
    };
  }
  return { name: TOOL_ALIAS[rawName] ?? rawName, args };
}

export type GeminiCloseInfo = {
  unexpected: boolean;
  recoverable: boolean;
  userMessage?: string;
  code?: number;
};

export type CedLiveConnectOptions = {
  voiceName?: string;
  language?: VoiceSessionPreferences["language"];
  responseSpeed?: VoiceSessionPreferences["responseSpeed"];
  voicePace?: VoiceSessionPreferences["voicePace"];
  voiceWarmth?: VoiceSessionPreferences["voiceWarmth"];
  voiceEnergy?: VoiceSessionPreferences["voiceEnergy"];
  voiceProfile?: VoiceSessionPreferences["voiceProfile"];
  /** Stream de micrófono con echoCancellation (WebRTC uplink). */
  micStream: MediaStream;
};

export type CedLiveHandlers = {
  onState?: (state: "connecting" | "connected" | "closed" | "error") => void;
  onSessionReady?: () => void;
  /** Saludo inicial terminado — habilitar escucha normal. */
  onGreetingComplete?: () => void;
  onTranscriptUpdate?: (text: string, role: "user" | "model") => void;
  onTranscript?: (text: string, role: "user" | "model") => void;
  /** WebRTC reproduce audio remoto; callback opcional para UI (inicio de respuesta). */
  onResponseStart?: () => void;
  /** Audio remoto terminó de transmitirse (antes de response.done). */
  onModelAudioDone?: () => void;
  onTurnComplete?: () => void;
  onInterrupted?: () => void;
  onSpeechStopped?: () => void;
  onToolStart?: (toolName: string) => void;
  onToolComplete?: () => void;
  onCameraIntent?: (intent: "activate" | "deactivate") => void;
  /** Tool request_camera_activation / deactivation desde OpenAI. */
  onCameraTool?: (intent: "activate" | "deactivate") => Promise<boolean>;
  onError?: (message: string) => void;
  onClose?: (info: GeminiCloseInfo) => void;
  shouldAllowAdvancedTool?: (toolPrompt: string) => boolean;
  onAdvancedToolBlocked?: (toolPrompt: string) => void;
  onLiveTool?: (
    name: string,
    args: Record<string, unknown>,
  ) => Promise<{ spoken?: string; ok?: boolean } | void>;
  onGeneratedImage?: (url: string, prompt?: string) => void;
  /** Resuelve imagen de referencia (cámara, última imagen, adjunto) para generate_image_with_reference. */
  onGenerateImageWithReference?: (
    args: Record<string, unknown>,
  ) => Promise<{ ok: boolean; url?: string; error?: string; spoken?: string }>;
};

function classifyPeerClose(unexpected: boolean): GeminiCloseInfo {
  if (!unexpected) {
    return { unexpected: false, recoverable: false };
  }
  return {
    unexpected: true,
    recoverable: true,
    userMessage: undefined,
  };
}

export class CedLiveClient {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private micStream: MediaStream | null = null;
  private sessionReady = false;
  private connectGen = 0;
  private connectInFlight = false;
  private intentionalClose = false;
  private sendBlocked = true;
  private model = "";
  private userTranscriptAcc = "";
  private modelTranscriptAcc = "";
  private processedCallIds = new Set<string>();
  private recentToolAt = new Map<string, number>();
  private activeResponseId: string | null = null;
  private responseInProgress = false;
  private videoStream: MediaStream | null = null;
  private videoSender: RTCRtpSender | null = null;
  private lastVideoFrameAt = 0;
  private static TOOL_COOLDOWN_MS = 2000;
  private static RESPONSE_IDLE_MS = 3200;
  private static VIDEO_FRAME_MIN_MS = 2000;
  private voiceProfile: VoiceSessionPreferences["voiceProfile"] = "jarvis";
  private userAddress: UserAddressContext | null = null;
  private handlers: CedLiveHandlers = {};
  private greetingSent = false;
  private greetingInFlight = false;
  private greetingComplete = false;
  private heardUserSinceGreeting = false;
  private greetingGraceUntil = 0;
  private outboundLocked = false;
  private awaitingFirstUserSpeech = false;
  private userTurnScheduled = false;
  private userResponseTimer: number | null = null;
  private intentionalResponse = false;
  private intentionalResponseActive = false;
  private blockAutoResponsesUntil = 0;
  /** "open" = esperando un response.id; string = único permitido; "closed" = normal */
  private singleSpeechSlot: "closed" | "open" | string = "closed";
  private advancedBriefInFlight = false;
  private userTurnResponded = false;
  private lastArmedTranscript = "";
  private turnCooldownUntil = 0;
  private lastResponseCreateAt = 0;
  private briefChain: Promise<void> = Promise.resolve();
  private toolsEnabled = true;

  isGreetingInProgress(): boolean {
    return (
      this.greetingInFlight ||
      (!this.greetingComplete && this.greetingSent) ||
      Date.now() < this.greetingGraceUntil
    );
  }

  private isLikelyBackgroundNoise(transcript: string): boolean {
    const t = transcript.trim().toLowerCase();
    if (!t || /^<noise>$/i.test(t)) return true;
    return (
      /gracias por ver|hasta la pr[oó]xima|nos vemos en|pr[oó]ximo video|suscr[ií]bete|dale like|thanks for watching|see you in the next|subscribe/i.test(
        t,
      ) || (t.length < 6 && /^(gracias|thanks|ok|sí|si|!|\.)+$/i.test(t))
    );
  }

  private isLikelyAmbientOrEcho(transcript: string): boolean {
    if (this.isLikelyBackgroundNoise(transcript)) return true;
    if (this.isLikelyGreetingEcho(transcript)) return true;
    const low = transcript.toLowerCase();
    return (
      (low.includes("buenos días") || low.includes("buenos dias")) &&
      (low.includes("ced") || low.includes("asistir"))
    ) || low.includes("listo para asistir") || low.includes("aquí ced");
  }

  private beginSingleSpeechSlot(): void {
    this.singleSpeechSlot = "open";
  }

  private endSingleSpeechSlot(): void {
    this.singleSpeechSlot = "closed";
  }

  private cancelResponse(responseId?: string | null): void {
    if (responseId) {
      this.send({ type: "response.cancel", response_id: responseId });
    } else {
      this.triggerBargeIn();
    }
  }

  /** Solo una response.created activa durante saludo/brief. */
  private allowResponseCreated(responseId?: string | null): boolean {
    const id = responseId ?? null;
    const inLockWindow =
      this.greetingInFlight ||
      this.outboundLocked ||
      Date.now() < this.blockAutoResponsesUntil;

    if (inLockWindow || this.singleSpeechSlot !== "closed") {
      if (this.singleSpeechSlot === "closed") {
        this.beginSingleSpeechSlot();
      }
      if (this.singleSpeechSlot === "open") {
        this.singleSpeechSlot = id ?? "unknown";
        return true;
      }
      if (id && this.singleSpeechSlot !== id) {
        cedRealtimeLog("response.reject.duplicate", { id, allowed: this.singleSpeechSlot });
        this.cancelResponse(id);
        return false;
      }
      return true;
    }

    if (this.responseInProgress && this.activeResponseId && id && id !== this.activeResponseId) {
      cedRealtimeLog("response.dedupe.cancel", { id });
      this.cancelResponse(id);
      return false;
    }
    return true;
  }

  /** Activa VAD solo cuando el micrófono del usuario está listo. */
  enableListeningAfterGreeting(): void {
    if (!this.sessionReady || this.sendBlocked) return;
    this.flushInputAudioBuffer();
    this.applyTurnDetection("listen");
    this.endSingleSpeechSlot();
  }

  private isLikelyGreetingEcho(transcript: string): boolean {
    if (!this.awaitingFirstUserSpeech && this.heardUserSinceGreeting) return false;
    const low = transcript.toLowerCase();
    return (
      low.includes("hola") &&
      (low.includes("señor") ||
        low.includes("senor") ||
        low.includes("señora") ||
        low.includes("en qué puedo ayudarle") ||
        low.includes("en que puedo ayudarle"))
    );
  }

  private markUserSpeechHeard(): void {
    if (this.awaitingFirstUserSpeech) {
      this.awaitingFirstUserSpeech = false;
    }
    this.heardUserSinceGreeting = true;
    this.blockAutoResponsesUntil = 0;
  }

  private isWellnessSmallTalk(transcript: string): boolean {
    const t = transcript.trim().toLowerCase();
    if (
      /\b(clima|temperatura|public|comentario|facebook|instagram|busca|ayuda|publicar|pdf|imagen|cámara|camara)\b/.test(
        t,
      )
    ) {
      return false;
    }
    return (
      t.length <= 72 &&
      /^(hola[,.\s!]*)?(muy )?(estoy )?(bien|fine|ok|gracias|thank you|thanks)/i.test(t)
    );
  }

  private resolveHonorific(): string {
    const h = this.userAddress?.honorific?.trim();
    const invalid = !h || h.length < 3 || /^(si|sí|sir|yes|ok)$/i.test(h.replace(/\./g, ""));
    if (!invalid) {
      if (/^(senor|señor)$/i.test(h)) return "Señor";
      if (/^(senora|señora)$/i.test(h)) return "Señora";
      return h;
    }
    if (this.userAddress?.gender === "female") return "Señora";
    return "Señor";
  }

  private briefTokensForSpoken(spoken: string, advanced = false): number {
    const min = advanced ? 680 : 180;
    return Math.min(900, Math.max(min, Math.ceil(spoken.length / 2.8)));
  }

  /** Respuesta fija a "bien/gracias" — evita "me alegra" repetido del modelo. */
  private async maybeReplyWellnessAck(transcript: string): Promise<boolean> {
    if (!this.greetingComplete || this.outboundLocked || !this.isWellnessSmallTalk(transcript)) {
      return false;
    }
    const phrase = `Entendido, ${this.resolveHonorific()}.`;
    await this.speakExactPhrase(phrase, 28);
    this.userTurnResponded = true;
    this.turnCooldownUntil = Date.now() + 6000;
    this.lastArmedTranscript = transcript.trim();
    return true;
  }

  /** Una sola response.create por turno — evita voces duplicadas. */
  private requestSingleResponse(): void {
    const now = Date.now();
    if (this.responseInProgress || this.outboundLocked) return;
    if (now < this.turnCooldownUntil) return;
    if (this.userTurnResponded && now - this.lastResponseCreateAt < 6000) return;
    if (now - this.lastResponseCreateAt < 1200) return;
    this.lastResponseCreateAt = now;
    this.userTurnResponded = true;
    this.turnCooldownUntil = now + 6000;
    this.intentionalResponse = true;
    this.intentionalResponseActive = true;
    cedRealtimeLog("response.create.single", {});
    this.send({
      type: "response.create",
      response: { max_output_tokens: 72 },
    });
  }

  private clearUserResponseTimer(): void {
    if (this.userResponseTimer) {
      window.clearTimeout(this.userResponseTimer);
      this.userResponseTimer = null;
    }
  }

  /** Espera fin de turno (debounce) — un solo response.create por intervención. */
  private armUserTurnResponse(transcript = ""): void {
    if (!this.greetingComplete || this.outboundLocked || this.greetingInFlight) return;
    if (this.responseInProgress || this.advancedBriefInFlight) return;
    if (Date.now() < this.turnCooldownUntil) return;
    const trimmed = transcript.trim();
    if (trimmed && trimmed === this.lastArmedTranscript) return;
    this.clearUserResponseTimer();
    this.userResponseTimer = window.setTimeout(() => {
      this.userResponseTimer = null;
      if (!this.greetingComplete || this.outboundLocked || this.responseInProgress) return;
      if (Date.now() < this.turnCooldownUntil) return;
      if (!this.heardUserSinceGreeting) return;
      if (trimmed) this.lastArmedTranscript = trimmed;
      void (async () => {
        if (trimmed && (await this.maybeReplyWellnessAck(trimmed))) return;
        this.requestSingleResponse();
      })();
    }, 1100);
  }

  /** Sesión Realtime creada sin herramientas (fallback API). */
  isToolsEnabled(): boolean {
    return this.toolsEnabled;
  }

  isOpen(): boolean {
    return Boolean(this.pc && this.sessionReady && !this.sendBlocked);
  }

  isResponseActive(): boolean {
    return this.responseInProgress;
  }

  /** Libera estado colgado si response.done no llegó (WebRTC). */
  forceReleaseTurn(): void {
    if (!this.responseInProgress && !this.activeResponseId) return;
    cedVoiceLog(4, "forceReleaseTurn — liberando respuesta colgada");
    this.activeResponseId = null;
    this.responseInProgress = false;
    this.flushInputAudioBuffer();
  }

  /** Compat — WebRTC maneja half-duplex con AEC nativo. */
  setBlockServerVad(_block: boolean): void {}

  setMicTrackEnabled(enabled: boolean): void {
    this.micStream?.getAudioTracks().forEach((t) => {
      t.enabled = enabled;
    });
  }

  setRemoteMuted(muted: boolean): void {
    if (this.remoteAudio) {
      this.remoteAudio.muted = muted;
    }
  }

  flushInputAudioBuffer(): void {
    this.send({ type: "input_audio_buffer.clear" });
  }

  /** Evita respuestas automáticas del servidor (p. ej. durante el saludo). */
  private applyTurnDetection(mode: "off" | "listen" | "auto"): void {
    if (!this.dc || this.dc.readyState !== "open") return;
    const turn_detection =
      mode === "off"
        ? null
        : {
            type: "semantic_vad" as const,
            eagerness: "medium" as const,
            create_response: mode === "auto",
            interrupt_response: true,
          };
    this.send({
      type: "session.update",
      session: {
        type: "realtime",
        audio: {
          input: {
            turn_detection,
          },
        },
      },
    });
  }

  private setServerAutoResponse(enabled: boolean): void {
    this.applyTurnDetection(enabled ? "auto" : "listen");
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.sessionReady = false;
    this.sendBlocked = true;
    this.greetingSent = false;
    this.greetingInFlight = false;
    this.greetingComplete = false;
    this.heardUserSinceGreeting = false;
    this.greetingGraceUntil = 0;
    this.awaitingFirstUserSpeech = false;
    this.clearUserResponseTimer();
    this.intentionalResponse = false;
    this.intentionalResponseActive = false;
    this.blockAutoResponsesUntil = 0;
    this.singleSpeechSlot = "closed";
    this.advancedBriefInFlight = false;
    this.userTurnResponded = false;
    this.lastArmedTranscript = "";
    this.turnCooldownUntil = 0;
    this.userTurnScheduled = false;
    this.lastResponseCreateAt = 0;
    this.connectGen += 1;

    this.dc?.close();
    this.dc = null;

    this.detachCameraStream();
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }

    if (this.remoteAudio) {
      this.remoteAudio.srcObject = null;
      this.remoteAudio = null;
    }

    voiceTelemetry.setWsState("disconnected");
    voiceTelemetry.setSessionId(null);
  }

  isCameraAttached(): boolean {
    return Boolean(this.videoSender && this.videoStream);
  }

  /** Agrega track de video al peer WebRTC (visión nativa Realtime). */
  async attachCameraStream(stream: MediaStream): Promise<boolean> {
    if (!this.pc || !stream.getVideoTracks().length) return false;
    const track = stream.getVideoTracks()[0];
    if (!track) return false;
    if ("contentHint" in track) {
      track.contentHint = "detail";
    }
    try {
      if (this.videoSender) {
        await this.videoSender.replaceTrack(track);
      } else {
        this.videoSender = this.pc.addTrack(track, stream);
      }
      this.videoStream = stream;
      this.notifyCameraContext(true);
      cedVoiceLog(5, "WebRTC video track attached");
      return true;
    } catch (err) {
      cedVoiceError("attachCameraStream failed", err);
      return false;
    }
  }

  /** Quita el track de video del peer WebRTC. */
  detachCameraStream(): void {
    const hadVideo = Boolean(this.videoSender);
    if (this.videoSender && this.pc) {
      try {
        this.pc.removeTrack(this.videoSender);
      } catch {
        /* ignore */
      }
    }
    this.videoSender = null;
    this.videoStream = null;
    if (hadVideo) {
      this.notifyCameraContext(false);
    }
  }

  private notifyCameraContext(active: boolean): void {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    const text = active
      ? "[CED sistema] Cámara ACTIVA. Para describir algo visual invoca analyze_camera_frame o buscar_lo_visible. " +
        "PROHIBIDO afirmar que ves sin invocar herramienta."
      : "[CED sistema] Cámara DESACTIVADA. PROHIBIDO decir que ves algo, al usuario o su entorno. " +
        "Si piden visión, invoca request_camera_activation.";
    this.send({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    });
  }

  async connect(
    handlers: CedLiveHandlers,
    options: CedLiveConnectOptions,
  ): Promise<boolean> {
    if (this.connectInFlight) return false;
    if (!options.micStream?.getAudioTracks().length) {
      handlers.onError?.("Micrófono no disponible para WebRTC.");
      return false;
    }

    this.connectInFlight = true;
    this.handlers = handlers;
    this.voiceProfile = options.voiceProfile ?? "jarvis";
    this.sendBlocked = true;
    this.disconnect();
    this.intentionalClose = false;
    this.micStream = options.micStream;
    this.userTranscriptAcc = "";
    this.modelTranscriptAcc = "";
    this.processedCallIds.clear();
    this.recentToolAt.clear();
    this.activeResponseId = null;
    this.responseInProgress = false;
    this.clearUserResponseTimer();
    this.intentionalResponse = false;
    this.userTurnResponded = false;
    this.lastArmedTranscript = "";
    this.turnCooldownUntil = 0;
    this.userTurnScheduled = false;
    this.lastResponseCreateAt = 0;

    const generation = this.connectGen;
    const isStale = () => generation !== this.connectGen;

    handlers.onState?.("connecting");
    voiceTelemetry.reset();
    voiceTelemetry.setWsState("connecting");
    voiceTelemetry.setSessionId(`openai-webrtc-${Date.now()}`);

    const tokenRes = await fetchEphemeralTokenCached(options.voiceName, {
      language: options.language,
      responseSpeed: options.responseSpeed,
      voicePace: options.voicePace,
      voiceWarmth: options.voiceWarmth,
      voiceEnergy: options.voiceEnergy,
      voiceProfile: options.voiceProfile,
    });
    if (isStale()) {
      this.connectInFlight = false;
      return false;
    }
    if (!tokenRes.ok) {
      handlers.onState?.("error");
      handlers.onError?.(tokenRes.error);
      voiceTelemetry.setWsState("error", tokenRes.error);
      this.connectInFlight = false;
      return false;
    }

    const voiceName = tokenRes.voiceName ?? "alloy";
    this.model = tokenRes.model;
    this.userAddress = tokenRes.userAddress ?? null;
    this.toolsEnabled = tokenRes.toolsEnabled !== false;
    if (!this.toolsEnabled) {
      cedVoiceError(
        "[REALTIME] Sesión SIN herramientas — publicar/imagen/búsqueda vía tools no funcionarán. Revisa logs API.",
      );
    }
    cedRealtimeLog("session.connect", {
      model: this.model,
      toolsEnabled: this.toolsEnabled,
      toolsCount: tokenRes.toolsCount ?? null,
      sessionVia: tokenRes.sessionVia ?? null,
    });
    voiceTelemetry.setActiveVoice(voiceName);

    try {
      const pc = new RTCPeerConnection();
      this.pc = pc;

      const remoteAudio = document.createElement("audio");
      remoteAudio.autoplay = true;
      remoteAudio.setAttribute("playsinline", "true");
      remoteAudio.preload = "auto";
      remoteAudio.volume = 1;
      this.remoteAudio = remoteAudio;

      pc.ontrack = (ev) => {
        const [stream] = ev.streams;
        if (stream && this.remoteAudio) {
          this.remoteAudio.srcObject = stream;
          void this.remoteAudio.play().catch(() => undefined);
          stream.getAudioTracks().forEach((track) => {
            cedRealtimeLog("audio.track", {
              label: track.label,
              enabled: track.enabled,
              muted: track.muted,
              readyState: track.readyState,
            });
          });
        }
      };

      pc.onconnectionstatechange = () => {
        if (isStale() || !this.pc) return;
        const state = this.pc.connectionState;
        cedVoiceLog(5, "WebRTC connection state", { state });
        if (state === "failed") {
          this.sessionReady = false;
          this.sendBlocked = true;
          handlers.onState?.("error");
          handlers.onError?.("Conexión WebRTC falló.");
          voiceTelemetry.setWsState("error", "webrtc failed");
          handlers.onClose?.(classifyPeerClose(true));
        }
        if (state === "disconnected" || state === "closed") {
          if (!this.intentionalClose) {
            this.sessionReady = false;
            this.sendBlocked = true;
            voiceTelemetry.setWsState("closed");
            handlers.onState?.("closed");
            handlers.onClose?.(classifyPeerClose(true));
          }
        }
      };

      options.micStream.getAudioTracks().forEach((track) => {
        pc.addTrack(track, options.micStream);
      });

      const dc = pc.createDataChannel("oai-events");
      this.dc = dc;

      const readyPromise = new Promise<boolean>((resolve) => {
        const readyTimeout = window.setTimeout(() => {
          if (!this.sessionReady && !isStale()) {
            handlers.onError?.("OpenAI no respondió a tiempo (WebRTC).");
            handlers.onState?.("error");
            resolve(false);
          }
        }, 20000);

        const markReady = () => {
          if (this.sessionReady || isStale()) return;
          window.clearTimeout(readyTimeout);
          this.sessionReady = true;
          this.sendBlocked = false;
          this.setServerAutoResponse(false);
          this.applyTurnDetection("off");
          this.flushInputAudioBuffer();
          voiceTelemetry.markSetupComplete();
          handlers.onState?.("connected");
          handlers.onSessionReady?.();
          cedVoiceLog(6, "OpenAI WebRTC session ready");
          this.connectInFlight = false;
          resolve(true);
        };

        dc.onopen = () => {
          cedVoiceLog(5, "WebRTC data channel open");
        };

        dc.onmessage = (ev) => {
          if (isStale()) return;
          try {
            const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
            void this.handleServerEvent(msg, markReady);
          } catch {
            /* ignore */
          }
        };

        dc.onclose = () => {
          if (!this.intentionalClose && !isStale()) {
            this.sessionReady = false;
            this.sendBlocked = true;
            voiceTelemetry.setWsState("closed");
            handlers.onState?.("closed");
            handlers.onClose?.(classifyPeerClose(true));
          }
        };
      });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const negotiate = await negotiateRealtimeCall(
        offer.sdp ?? "",
        tokenRes.clientSecret,
      );
      if (isStale()) {
        this.connectInFlight = false;
        return false;
      }
      if (!negotiate.ok) {
        handlers.onState?.("error");
        handlers.onError?.(negotiate.error);
        voiceTelemetry.setWsState("error", negotiate.error);
        this.connectInFlight = false;
        return false;
      }

      await pc.setRemoteDescription({
        type: "answer",
        sdp: negotiate.sdpAnswer,
      });

      voiceTelemetry.setWsState("connected");
      cedVoiceLog(5, "WebRTC negociado", { model: this.model, voice: voiceName });

      return await readyPromise;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error WebRTC";
      cedVoiceError("[OPENAI:WebRTC]", msg);
      handlers.onState?.("error");
      handlers.onError?.(msg);
      voiceTelemetry.setWsState("error", msg);
      this.connectInFlight = false;
      return false;
    }
  }

  private async handleServerEvent(
    msg: Record<string, unknown>,
    markReady: () => void,
  ): Promise<void> {
    const handlers = this.handlers;
    const type = String(msg.type ?? "");

    cedRealtimeLog("event", { type });

    if (type === "session.created") {
      const session = msg.session as { tools?: unknown[] } | undefined;
      const toolsCount = session?.tools?.length ?? 0;
      if (toolsCount > 0) this.toolsEnabled = true;
      cedRealtimeLog("session.ready", { type, toolsCount, toolsEnabled: this.toolsEnabled });
      markReady();
      return;
    }

    if (type === "session.updated") {
      const session = msg.session as { tools?: unknown[] } | undefined;
      const toolsCount = session?.tools?.length ?? 0;
      if (toolsCount > 0) this.toolsEnabled = true;
      cedRealtimeLog("session.updated", { toolsCount, toolsEnabled: this.toolsEnabled });
      return;
    }

    if (type === "response.function_call_arguments.delta") {
      cedRealtimeLog("tool.args.delta", { delta: String(msg.delta ?? "").slice(0, 120) });
      return;
    }

    if (type === "response.output_item.done") {
      const item = msg.item as
        | { type?: string; name?: string; call_id?: string; arguments?: string }
        | undefined;
      if (item?.type === "function_call" && item.call_id && item.name) {
        cedRealtimeLog("tool.output_item.done", {
          name: item.name,
          call_id: item.call_id,
        });
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(String(item.arguments ?? "{}")) as Record<string, unknown>;
        } catch {
          args = {};
        }
        await this.dispatchTool(item.name, item.call_id, args);
      }
      return;
    }

    if (type === "response.created") {
      const response = msg.response as { id?: string } | undefined;
      if (!this.allowResponseCreated(response?.id)) {
        return;
      }
      this.activeResponseId = response?.id ?? null;
      this.responseInProgress = true;
      handlers.onResponseStart?.();
      return;
    }

    if (isResponseAudioTranscriptDelta(type)) {
      const delta = String(msg.delta ?? "");
      this.modelTranscriptAcc += delta;
      if (delta) handlers.onTranscriptUpdate?.(this.modelTranscriptAcc, "model");
      return;
    }

    if (isResponseAudioDone(type)) {
      handlers.onModelAudioDone?.();
      return;
    }

    if (isInputTranscriptionCompleted(type)) {
      const transcript = String(msg.transcript ?? "").trim();
      if (transcript && !this.isLikelyAmbientOrEcho(transcript)) {
        this.markUserSpeechHeard();
        this.userTranscriptAcc = transcript;
        handlers.onTranscriptUpdate?.(transcript, "user");
        const intent = parseCameraIntent(transcript);
        if (intent) handlers.onCameraIntent?.(intent);
        if (this.greetingComplete && !this.outboundLocked && Date.now() >= this.blockAutoResponsesUntil) {
          void this.armUserTurnResponse(transcript);
        }
      } else if (transcript) {
        cedRealtimeLog("transcript.ignored", { transcript: transcript.slice(0, 80) });
        this.flushInputAudioBuffer();
      }
      return;
    }

    if (type === "input_audio_buffer.speech_started") {
      if (
        this.greetingComplete &&
        !this.responseInProgress &&
        Date.now() - this.lastResponseCreateAt > 3500 &&
        Date.now() > this.turnCooldownUntil
      ) {
        this.awaitingFirstUserSpeech = false;
        this.userTurnResponded = false;
        this.lastArmedTranscript = "";
      }
      return;
    }

    if (type === "input_audio_buffer.speech_stopped") {
      handlers.onSpeechStopped?.();
      return;
    }

    if (type === "response.cancelled") {
      this.activeResponseId = null;
      this.responseInProgress = false;
      this.flushInputAudioBuffer();
      handlers.onInterrupted?.();
      return;
    }

    if (type === "response.done") {
      const response = msg.response as
        | { status?: string; status_details?: unknown }
        | undefined;
      if (response?.status === "cancelled") {
        cedVoiceLog(5, "OpenAI response cancelled");
      }
      if (response?.status === "failed") {
        cedVoiceError("[REALTIME] response.failed", response.status_details);
      }
      cedRealtimeLog("response.done", {
        status: response?.status ?? "unknown",
      });
      this.activeResponseId = null;
      this.responseInProgress = false;
      this.intentionalResponse = false;
      this.intentionalResponseActive = false;
      this.advancedBriefInFlight = false;
      this.userTurnScheduled = false;
      if (this.modelTranscriptAcc.trim()) {
        handlers.onTranscript?.(this.modelTranscriptAcc.trim(), "model");
        this.modelTranscriptAcc = "";
      }
      if (this.userTranscriptAcc.trim()) {
        handlers.onTranscript?.(this.userTranscriptAcc.trim(), "user");
        this.userTranscriptAcc = "";
      }
      voiceTelemetry.markTurnComplete();
      handlers.onTurnComplete?.();
      return;
    }

    if (type === "response.function_call_arguments.done") {
      const callId = String(msg.call_id ?? "");
      const name = String(msg.name ?? "");
      cedRealtimeLog("tool.args.done", {
        name,
        call_id: callId,
        arguments: String(msg.arguments ?? "").slice(0, 240),
      });
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(String(msg.arguments ?? "{}")) as Record<string, unknown>;
      } catch {
        args = {};
      }
      await this.dispatchTool(name, callId, args);
      return;
    }

    if (type === "error") {
      const err = msg.error as { message?: string } | undefined;
      const message = err?.message ?? "Realtime error";
      if (isBenignRealtimeError(message)) {
        cedVoiceLog(5, "OpenAI benign error ignored", { message });
        return;
      }
      voiceTelemetry.setWsState("error", message);
      handlers.onError?.(message);
    }
  }

  sendVideoJpeg(base64Jpeg: string): void {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    const now = Date.now();
    if (now - this.lastVideoFrameAt < CedLiveClient.VIDEO_FRAME_MIN_MS) return;
    const trimmed = base64Jpeg.trim();
    if (!trimmed) return;
    this.lastVideoFrameAt = now;
    const url = trimmed.startsWith("data:")
      ? trimmed
      : `data:image/jpeg;base64,${trimmed}`;
    this.send({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_image", image_url: url }],
      },
    });
  }

  sendAdvancedSystemAck(): void {
    if (this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(CED_VOICE_PROFILE_LOCK.advancedSystem.ackInstruction);
  }

  setUserAddress(address: UserAddressContext | null): void {
    this.userAddress = address;
  }

  getUserAddress(): UserAddressContext | null {
    return this.userAddress;
  }

  isAwaitingFirstUserSpeech(): boolean {
    return this.awaitingFirstUserSpeech;
  }

  sendSessionGreeting(): void {
    if (
      this.greetingSent ||
      this.greetingInFlight ||
      !this.dc ||
      !this.sessionReady ||
      this.sendBlocked
    ) {
      return;
    }
    this.greetingSent = true;
    this.greetingInFlight = true;
    void (async () => {
      try {
        this.applyTurnDetection("off");
        this.setMicTrackEnabled(false);
        this.flushInputAudioBuffer();
        const phrase = cedReceptionGreetingPhrase(this.voiceProfile, this.userAddress);
        if (this.responseInProgress) {
          this.triggerBargeIn();
          await this.waitForResponseIdle(1200);
        }
        this.blockAutoResponsesUntil = Date.now() + 14_000;
        this.beginSingleSpeechSlot();
        cedRealtimeLog("greeting.create", { phrase });
        await this.speakExactPhrase(phrase, 52);
        this.flushInputAudioBuffer();
        this.greetingGraceUntil = Date.now() + 6_000;
        this.greetingComplete = true;
        this.awaitingFirstUserSpeech = true;
        this.turnCooldownUntil = Date.now() + 3500;
        this.handlers.onGreetingComplete?.();
      } finally {
        this.greetingInFlight = false;
      }
    })();
  }

  /** Una sola frase exacta — fuera del historial de conversación. */
  private async speakExactPhrase(phrase: string, maxOutputTokens = 100): Promise<void> {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    this.outboundLocked = true;
    this.setServerAutoResponse(false);
    if (this.singleSpeechSlot === "closed") {
      this.beginSingleSpeechSlot();
    }
    try {
      this.send({
        type: "response.create",
        response: {
          conversation: "none",
          max_output_tokens: maxOutputTokens,
          tool_choice: "none",
          instructions:
            `Pronuncia ÚNICAMENTE este texto en español, sin añadir ni quitar palabras. ` +
            `PROHIBIDO: "cómo está", buenos días/tardes/noches, "me alegra", "aquí CED", inglés. ` +
            `Texto exacto: "${phrase.trim()}"`,
        },
      });
      await this.waitForResponseIdle(12000);
      await this.sleep(800);
      this.flushInputAudioBuffer();
    } finally {
      this.outboundLocked = false;
    }
  }

  /** Presencia tras silencio — una frase exacta. */
  sendPresenceBrief(phrase: string): void {
    const text = phrase.trim();
    if (!text || this.greetingInFlight) return;
    void (async () => {
      await this.speakExactPhrase(text, 60);
    })();
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private enqueueControlledBrief(
    turnText: string,
    maxOutputTokens = 400,
  ): Promise<void> {
    const task = async () => {
      await this.sendControlledBrief(turnText, maxOutputTokens);
    };
    this.briefChain = this.briefChain.then(task, task);
    return this.briefChain;
  }

  private async sendControlledBrief(
    turnText: string,
    maxOutputTokens = 400,
  ): Promise<void> {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    this.outboundLocked = true;
    this.advancedBriefInFlight = maxOutputTokens > 400;
    this.blockAutoResponsesUntil = Date.now() + Math.max(12000, maxOutputTokens * 40);
    this.beginSingleSpeechSlot();
    try {
      if (this.responseInProgress) {
        this.triggerBargeIn();
        await this.waitForResponseIdle();
      }
      this.setServerAutoResponse(false);
      this.send({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: turnText }],
        },
      });
      this.intentionalResponse = true;
      this.intentionalResponseActive = true;
      this.send({
        type: "response.create",
        response: {
          max_output_tokens: maxOutputTokens,
          tool_choice: "none",
        },
      });
      this.lastResponseCreateAt = Date.now();
      const idleMs = maxOutputTokens > 400 ? 48000 : 18000;
      await this.waitForResponseIdle(idleMs);
      await this.sleep(500);
      this.flushInputAudioBuffer();
      this.turnCooldownUntil = Date.now() + 5000;
    } finally {
      this.outboundLocked = false;
      this.advancedBriefInFlight = false;
    }
  }

  sendNarrationBrief(summary: string): void {
    const text = summary.trim();
    if (!text || this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(cedBriefTurn(text));
  }

  sendPublishConfirm(platform: "facebook" | "instagram"): void {
    if (this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(cedPublishConfirmTurn(platform));
  }

  sendWebSearchAck(): void {
    /* Obsoleto — provocaba doble respuesta (ack + brief). Usar solo sendNarrationBrief. */
  }

  triggerBargeIn(): void {
    if (!this.responseInProgress) return;
    const cancel: Record<string, unknown> = { type: "response.cancel" };
    if (this.activeResponseId) cancel.response_id = this.activeResponseId;
    this.send(cancel);
  }

  private waitForResponseIdle(maxMs = CedLiveClient.RESPONSE_IDLE_MS): Promise<void> {
    if (!this.responseInProgress) return Promise.resolve();
    return new Promise((resolve) => {
      const start = performance.now();
      const tick = () => {
        if (!this.responseInProgress || performance.now() - start > maxMs) {
          if (this.responseInProgress && performance.now() - start > maxMs) {
            this.forceReleaseTurn();
          }
          resolve();
          return;
        }
        setTimeout(tick, 40);
      };
      tick();
    });
  }

  private async sendClientTurn(text: string): Promise<void> {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    if (this.responseInProgress) {
      cedVoiceLog(5, "Cancelando respuesta previa antes de nuevo turno CED");
      this.triggerBargeIn();
      await this.waitForResponseIdle();
    }
    try {
      this.send({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text }],
        },
      });
      this.send({ type: "response.create" });
    } catch (err) {
      cedVoiceError("sendClientTurn failed", err);
    }
  }

  private send(payload: Record<string, unknown>): void {
    if (!this.dc || this.dc.readyState !== "open") return;
    this.dc.send(JSON.stringify(payload));
  }

  private dispatchVoiceToolResult(
    toolName: string,
    result: Record<string, unknown>,
  ): void {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("ced-voice-tool-result", {
        detail: { tool_name: toolName, result },
      }),
    );
  }

  private async dispatchTool(
    rawName: string,
    callId: string,
    args: Record<string, unknown>,
  ): Promise<void> {
    if (!callId) {
      cedRealtimeLog("tool.skip", { reason: "missing call_id", name: rawName });
      return;
    }
    if (this.processedCallIds.has(callId)) {
      cedRealtimeLog("tool.skip", { reason: "duplicate call_id", call_id: callId, name: rawName });
      return;
    }
    const dedupeKey = `${rawName}:${JSON.stringify(args)}`;
    const lastAt = this.recentToolAt.get(dedupeKey) ?? 0;
    if (Date.now() - lastAt < CedLiveClient.TOOL_COOLDOWN_MS) {
      cedRealtimeLog("tool.skip", { reason: "cooldown", name: rawName, dedupeKey });
      return;
    }
    this.recentToolAt.set(dedupeKey, Date.now());
    this.processedCallIds.add(callId);

    const h = this.handlers;
    const normalized = normalizeToolInvocation(rawName, args);
    const name = normalized.name;
    args = normalized.args;
    cedRealtimeLog("tool.execute", { name: rawName, resolved: name, call_id: callId, args });

    try {
      if (rawName === "search_web") {
        const query = String(args.query ?? "").trim();
        h.onToolStart?.("search_web");
        const brief = await fetchVoiceBrief(query || "noticias hoy", "news");
        const spoken = brief.ok ? brief.summary : "No pude buscar en internet.";
        await this.submitToolOutput(callId, { status: "ok", spoken });
        return;
      }

      if (rawName === "request_camera_activation") {
        h.onToolStart?.("request_camera_activation");
        const ok = (await h.onCameraTool?.("activate")) ?? false;
        await this.submitToolOutput(callId, {
          status: ok ? "ok" : "error",
          spoken: ok
            ? "Cámara activa."
            : "No pude activar la cámara. Revisa permisos del navegador.",
        });
        return;
      }

      if (rawName === "request_camera_deactivation") {
        h.onToolStart?.("request_camera_deactivation");
        await h.onCameraTool?.("deactivate");
        await this.submitToolOutput(callId, {
          status: "ok",
          spoken: "Cámara apagada.",
        });
        return;
      }

      if (rawName === "generate_image") {
        const prompt = String(args.prompt ?? "").trim();
        const quality = String(args.quality ?? "auto");
        h.onToolStart?.("generate_image");
        const result = await fetchGenerateImage(
          prompt || "imagen creativa",
          quality as "auto" | "standard" | "hd",
        );
        if (result.ok) {
          h.onGeneratedImage?.(result.url, prompt);
          const hTitle = this.userAddress?.honorific?.trim() || "Señor";
          const toolResult = {
            status: "ok",
            spoken: `Imagen generada, ${hTitle}.`,
            image_url: result.url,
            prompt,
          };
          this.dispatchVoiceToolResult("generate_image", toolResult);
          await this.submitToolOutput(callId, toolResult);
        } else {
          const toolResult = {
            status: "error",
            spoken: result.error || "No pude generar la imagen.",
          };
          this.dispatchVoiceToolResult("generate_image", toolResult);
          await this.submitToolOutput(callId, toolResult);
        }
        return;
      }

      if (rawName === "generate_image_with_reference") {
        h.onToolStart?.("generate_image_with_reference");
        if (h.onGenerateImageWithReference) {
          const result = await h.onGenerateImageWithReference(args);
          if (result.ok && result.url) {
            h.onGeneratedImage?.(result.url, String(args.prompt ?? ""));
            await this.submitToolOutput(callId, {
              status: "ok",
              spoken: result.spoken || "Ahí está.",
              image_url: result.url,
            });
          } else {
            await this.submitToolOutput(callId, {
              status: "error",
              spoken: result.error || result.spoken || "No pude generar con la referencia.",
            });
          }
        } else {
          await this.submitToolOutput(callId, {
            status: "error",
            spoken: "No tengo acceso a la imagen de referencia. Muéstrame o adjunta una imagen primero.",
          });
        }
        return;
      }

      if (name === CONSULTAR_SISTEMA_AVANZADO) {
        const prompt = String(args.prompt ?? args.query ?? "").trim();
        const allowed = h.shouldAllowAdvancedTool?.(prompt) ?? false;
        if (!allowed) {
          h.onAdvancedToolBlocked?.(prompt);
          if (this.responseInProgress) {
            this.triggerBargeIn();
            await this.waitForResponseIdle(1600);
          }
          await this.speakExactPhrase(CED_ADVANCED_CONFIRM_PHRASE, 36);
          await this.submitToolOutput(callId, {
            status: "needs_confirmation",
            prompt,
            silent: true,
          });
          return;
        }
        h.onToolStart?.(name);
        if (this.responseInProgress) {
          this.triggerBargeIn();
          await this.waitForResponseIdle(2400);
        }
        await this.speakExactPhrase(`Un momento, ${this.resolveHonorific()}.`, 32);
        const result = await fetchDeepAnalysis(
          prompt || "consulta general",
          CED_VOICE_PROFILE_LOCK.advancedSystem.fetchTimeoutMs,
        );
        const spoken = result.ok ? result.result : "No pude completar el análisis.";
        await this.submitToolOutput(callId, {
          status: result.ok ? "ok" : "error",
          spoken,
          briefOnly: true,
          advancedBrief: true,
        });
        return;
      }

      if (LIVE_TOOL_NAMES.has(name) && h.onLiveTool) {
        h.onToolStart?.(name);
        const result = await h.onLiveTool(name, args);
        const success = result?.ok !== false;
        let spoken = (result?.spoken ?? "").trim();
        if (name === PUBLICAR_FACEBOOK) {
          spoken = success
            ? cedPublishSuccessPhrase("facebook", this.userAddress)
            : cedPublishFailurePhrase(spoken || "no fue posible completar la publicación", this.userAddress);
        } else if (name === PUBLICAR_INSTAGRAM) {
          spoken = success
            ? cedPublishSuccessPhrase("instagram", this.userAddress)
            : cedPublishFailurePhrase(spoken || "no fue posible completar la publicación", this.userAddress);
        } else if (!spoken) {
          spoken = success ? "Operación completada." : "No pude completar la operación.";
        }
        const toolResult = {
          status: success ? "ok" : "error",
          spoken,
          success,
        };
        this.dispatchVoiceToolResult(name, toolResult);
        await this.submitToolOutput(callId, toolResult);
        return;
      }

      const unknown = { status: "unknown_tool", name: rawName };
      cedRealtimeLog("tool.unknown", { name: rawName });
      await this.submitToolOutput(callId, unknown);
    } catch (error) {
      cedVoiceError("[REALTIME] tool execution failed", error);
      const message = error instanceof Error ? error.message : "Error al ejecutar herramienta";
      await this.submitToolOutput(callId, {
        status: "error",
        spoken: message,
        success: false,
      });
    } finally {
      h.onToolComplete?.();
    }
  }

  private async submitToolOutput(
    callId: string,
    output: Record<string, unknown>,
  ): Promise<void> {
    if (this.responseInProgress && !output.advancedBrief) {
      cedRealtimeLog("tool.output.wait_idle", { call_id: callId });
      await this.waitForResponseIdle(1600);
    }
    const spoken =
      typeof output.spoken === "string" ? output.spoken.trim() : "";
    const briefOnly = output.briefOnly === true;
    const advancedBrief = output.advancedBrief === true;
    const silent = output.silent === true;
    const payload: Record<string, unknown> = {
      status: output.status,
      success: output.status === "ok" || output.success === true,
    };
    if (output.prompt) payload.prompt = output.prompt;
    if (spoken) {
      payload.spoken = spoken;
      payload.delivery =
        "SILENCIO OBLIGATORIO. NO narres ni resumas este resultado en voz. " +
        "El cliente leerá el texto vía [CED_BRIEF]. Permanece en silencio.";
    }

    const outputMessage = {
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: callId,
        output: JSON.stringify(payload),
      },
    };
    cedRealtimeLog("tool.output.send", { call_id: callId, payload });
    this.send(outputMessage);

    if (spoken && (briefOnly || advancedBrief)) {
      cedRealtimeLog("tool.response.brief", { call_id: callId, advanced: advancedBrief });
      const turn = advancedBrief ? cedAdvancedBriefTurn(spoken) : cedBriefTurn(spoken);
      const tokens = this.briefTokensForSpoken(spoken, advancedBrief);
      this.turnCooldownUntil = Date.now() + Math.min(18000, 5000 + spoken.length * 12);
      await this.enqueueControlledBrief(turn, tokens);
      return;
    }

    if (spoken) {
      cedRealtimeLog("tool.response.brief", { call_id: callId, spoken });
      await this.enqueueControlledBrief(cedBriefTurn(spoken), this.briefTokensForSpoken(spoken));
      return;
    }

    if (!silent) {
      cedRealtimeLog("tool.response.create", { call_id: callId });
      this.requestSingleResponse();
    }
  }
}

