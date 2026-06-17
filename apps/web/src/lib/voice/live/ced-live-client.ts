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
  cedGreetingBriefTurn,
  cedPublishConfirmTurn,
  cedPublishFailurePhrase,
  cedPublishSuccessPhrase,
  cedReceptionGreetingPhrase,
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
  private briefChain: Promise<void> = Promise.resolve();
  private toolsEnabled = true;

  isGreetingInProgress(): boolean {
    return (
      this.greetingInFlight ||
      (!this.greetingComplete && this.greetingSent) ||
      Date.now() < this.greetingGraceUntil
    );
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
  private setServerAutoResponse(enabled: boolean): void {
    if (!this.dc || this.dc.readyState !== "open") return;
    this.send({
      type: "session.update",
      session: {
        type: "realtime",
        audio: {
          input: {
            turn_detection: {
              type: "semantic_vad",
              eagerness: "medium",
              create_response: enabled,
              interrupt_response: true,
            },
          },
        },
      },
    });
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
      if (
        !this.outboundLocked &&
        !this.greetingInFlight &&
        this.greetingComplete &&
        !this.heardUserSinceGreeting &&
        Date.now() > this.greetingGraceUntil
      ) {
        cedRealtimeLog("greeting.cancel_unsolicited", { id: response?.id });
        this.triggerBargeIn();
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
      const transcript = String(msg.transcript ?? "");
      if (transcript.trim()) {
        this.heardUserSinceGreeting = true;
        this.userTranscriptAcc = transcript.trim();
        handlers.onTranscriptUpdate?.(transcript.trim(), "user");
        const intent = parseCameraIntent(transcript.trim());
        if (intent) handlers.onCameraIntent?.(intent);
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
        this.setServerAutoResponse(false);
        this.setMicTrackEnabled(false);
        this.flushInputAudioBuffer();
        const phrase = cedReceptionGreetingPhrase(this.voiceProfile, this.userAddress);
        const turn = cedGreetingBriefTurn(phrase);
        if (this.responseInProgress) {
          this.triggerBargeIn();
          await this.waitForResponseIdle(1200);
        }
        cedRealtimeLog("greeting.create", { phrase });
        await this.sendControlledBrief(turn, 450);
        await this.sleep(2200);
        this.flushInputAudioBuffer();
        this.greetingGraceUntil = Date.now() + 10_000;
        this.greetingComplete = true;
        this.setServerAutoResponse(true);
        this.handlers.onGreetingComplete?.();
      } finally {
        this.greetingInFlight = false;
      }
    })();
  }

  /** Presencia tras silencio — una frase exacta, sin improvisar. */
  sendPresenceBrief(phrase: string): void {
    const text = phrase.trim();
    if (!text || this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(cedBriefTurn(text), 80);
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
      this.send({
        type: "response.create",
        response: {
          max_output_tokens: maxOutputTokens,
          tool_choice: "none",
        },
      });
      await this.waitForResponseIdle(18000);
      await this.sleep(400);
      this.flushInputAudioBuffer();
    } finally {
      this.outboundLocked = false;
      if (this.greetingComplete) {
        this.setServerAutoResponse(true);
      }
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
          await this.submitToolOutput(callId, {
            status: "needs_confirmation",
            spoken: CED_ADVANCED_CONFIRM_PHRASE,
            prompt,
          });
          return;
        }
        h.onToolStart?.(name);
        const result = await fetchDeepAnalysis(
          prompt || "consulta general",
          CED_VOICE_PROFILE_LOCK.advancedSystem.fetchTimeoutMs,
        );
        const spoken = result.ok ? result.result : "No pude completar el análisis.";
        await this.submitToolOutput(callId, {
          status: result.ok ? "ok" : "error",
          spoken,
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
    if (this.responseInProgress) {
      cedRealtimeLog("tool.output.wait_idle", { call_id: callId });
      await this.waitForResponseIdle(1600);
    }
    const spoken =
      typeof output.spoken === "string" ? output.spoken.trim() : "";
    const payload: Record<string, unknown> = {
      ...output,
      success: output.status === "ok" || output.success === true,
    };
    if (spoken) {
      payload.delivery =
        "OBLIGATORIO: di en voz alta la confirmación. No omitas ni te quedes en silencio.";
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

    if (spoken) {
      cedRealtimeLog("tool.response.brief", { call_id: callId, spoken });
      await this.enqueueControlledBrief(cedBriefTurn(spoken), 160);
      return;
    }

    cedRealtimeLog("tool.response.create", { call_id: callId });
    this.send({ type: "response.create" });
  }
}

