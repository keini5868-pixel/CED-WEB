import { RetellWebClient, type StartCallConfig } from "retell-client-js-sdk";

import { sanitizeHudTranscript } from "@/lib/voice/hud-transcript-filter";
import {
  inferRetellTransport,
  mapRetellClientError,
  type RetellIceServer,
} from "@/lib/voice/retell/retell-transport";

/** Tipos mínimos — livekit-client es transitiva vía retell; no importar directo (rompe next build). */
type RetellLiveRoom = {
  remoteParticipants: Map<
    string,
    {
      audioTrackPublications: Map<
        string,
        { trackName?: string; track?: { setVolume?(volume: number): void } }
      >;
    }
  >;
};
export type RetellTranscriptRole = "user" | "agent";

export interface CedRetellCallbacks {
  onCallStarted?: () => void;
  onCallEnded?: () => void;
  onAgentTalking?: (talking: boolean) => void;
  onTranscript?: (
    text: string,
    role: RetellTranscriptRole,
    options?: { partial?: boolean; streamKey?: string; incomplete?: boolean },
  ) => void;
  /** Retracta bubble agent activo cuando el usuario interrumpe. */
  onClearAgentPartial?: () => void;
  onError?: (message: string) => void;
  onAudioLevel?: (level: number) => void;
}

type RetellUpdateEvent = {
  transcript?: Array<{ role?: string; content?: string }>;
  turntaking?: string;
};

export type RetellCallMediaOptions = {
  transport?: "livekit" | "gateway" | null;
  ice_servers?: RetellIceServer[] | null;
  url?: string | null;
  identity?: string | null;
};

type RetellSdkHandle = {
  room?: RetellLiveRoom;
  transport?: {
    room?: RetellLiveRoom;
    audioEl?: HTMLAudioElement;
  };
};

function retellLog(message: string, detail?: unknown): void {
  if (detail !== undefined) {
    console.log(`[CED:RETELL] ${message}`, detail);
  } else {
    console.log(`[CED:RETELL] ${message}`);
  }
}

/** Limpia artefactos STT del agente antes de emitir al HUD. */
function sanitizeAgentStt(text: string): { text: string; incomplete: boolean } {
  let cleaned = text.trim();
  if (!cleaned) {
    return { text: "", incomplete: false };
  }

  if (cleaned.startsWith("[") && !cleaned.includes("]")) {
    cleaned = cleaned.slice(1).trimStart();
  }

  const incomplete =
    cleaned.length > 0 && !/[.!?…]["']?$/.test(cleaned);
  return { text: cleaned, incomplete };
}

export class CedRetellClient {
  private client: RetellWebClient;
  private callId: string | null = null;
  private callbacks: CedRetellCallbacks = {};
  private levelRaf: number | null = null;
  private lastUserLine = "";
  private lastAgentLine = "";
  private lastPersistedAgentLine = "";
  private lastPersistedUserLine = "";
  private pendingUserText = "";
  private userDebounceTimer: number | null = null;
  private audioRetryTimer: number | null = null;
  private agentAudioReady = false;
  private liveKitConnected = false;
  private audioPlaybackStarted = false;
  private agentSpeaking = false;
  private agentMutedForBargeIn = false;
  /** YouTube activo: mic mute + agent volume 0 (anti AGC/USB pump). */
  private youtubeMediaMode = false;
  private agentTurnSeq = 0;
  private currentAgentStreamKey = "";
  private lastTurntaking = "";
  private userTurnSeq = 0;
  private currentUserStreamKey = "";
  private lastAgentPartialEmitAt = 0;
  private lastEmittedAgentPartial = "";

  constructor() {
    this.client = new RetellWebClient();
    this.setupListeners();
  }

  setCallbacks(callbacks: CedRetellCallbacks): void {
    this.callbacks = callbacks;
  }

  private liveKitRoom(): RetellLiveRoom | undefined {
    const handle = this.client as unknown as RetellSdkHandle;
    return handle.room ?? handle.transport?.room;
  }

  private setAgentTrackVolume(volume: number): void {
    try {
      const handle = this.client as unknown as RetellSdkHandle;
      const audioEl = handle.transport?.audioEl;
      if (audioEl) audioEl.volume = volume;
      const room = this.liveKitRoom();
      if (!room) return;
      room.remoteParticipants.forEach((participant) => {
        participant.audioTrackPublications.forEach((publication) => {
          if (publication.trackName !== "agent_audio") return;
          publication.track?.setVolume?.(volume);
        });
      });
    } catch (err) {
      retellLog("setAgentTrackVolume falló", err);
    }
  }

  private muteAgentPlayback(): void {
    this.setAgentTrackVolume(0);
    this.agentMutedForBargeIn = true;
    retellLog("barge-in: agent audio silenciado");
  }

  private restoreAgentPlayback(): void {
    if (!this.agentMutedForBargeIn) return;
    // YouTube manda: no devolver volumen del agente mientras suene música.
    if (!this.youtubeMediaMode) {
      this.setAgentTrackVolume(1);
    }
    this.agentMutedForBargeIn = false;
  }

  private maybeBargeIn(): void {
    // Claude-like: si el usuario empieza a hablar, CED se calla al instante.
    // Retell corta el TTS en servidor; el mute local evita el solape audible.
    if (this.youtubeMediaMode) return;
    if (!this.agentSpeaking) return;
    this.muteAgentPlayback();
    this.callbacks.onClearAgentPartial?.();
  }

  private stopAudioRetry(): void {
    if (this.audioRetryTimer != null) {
      window.clearInterval(this.audioRetryTimer);
      this.audioRetryTimer = null;
    }
  }

  private clearUserDebounce(): void {
    if (this.userDebounceTimer != null) {
      window.clearTimeout(this.userDebounceTimer);
      this.userDebounceTimer = null;
    }
  }

  private flushUserTranscript(force = false): void {
    if (force) {
      this.clearUserDebounce();
    }
    const text = this.pendingUserText.trim();
    if (!text) return;
    this.persistUserLine(text);
  }

  /** Una sola línea por turno de usuario — evita parcial + final duplicados. */
  private persistUserLine(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (trimmed === this.lastPersistedUserLine) return;

    const prev = this.lastPersistedUserLine.trim();
    if (prev && trimmed.startsWith(prev) && trimmed.length > prev.length) {
      // Extensión del mismo turno (STT refinando texto).
    } else if (prev && prev.startsWith(trimmed)) {
      return;
    } else {
      this.userTurnSeq += 1;
      this.currentUserStreamKey = `user-${this.userTurnSeq}`;
    }

    if (!this.currentUserStreamKey) {
      this.userTurnSeq += 1;
      this.currentUserStreamKey = `user-${this.userTurnSeq}`;
    }

    this.lastPersistedUserLine = trimmed;
    this.lastUserLine = trimmed;
    this.currentAgentStreamKey = "";
    this.lastAgentLine = "";
    this.callbacks.onClearAgentPartial?.();
    this.callbacks.onTranscript?.(trimmed, "user", {
      partial: false,
      streamKey: this.currentUserStreamKey,
    });
  }

  private scheduleUserTranscript(text: string): void {
    if (text === this.pendingUserText) return;
    this.pendingUserText = text;
    this.clearUserDebounce();
    this.userDebounceTimer = window.setTimeout(() => {
      this.flushUserTranscript(false);
    }, 900);
  }

  /** Una sola vez tras call_ready — evita zumbido por startAudioPlayback repetido. */
  private ensureAudioPlayback(): void {
    if (!this.liveKitConnected || !this.agentAudioReady || this.audioPlaybackStarted) return;
    this.audioPlaybackStarted = true;
    void this.client.startAudioPlayback().catch((err) => {
      this.audioPlaybackStarted = false;
      retellLog("startAudioPlayback falló — reintento", err);
      window.setTimeout(() => {
        if (!this.audioPlaybackStarted && this.agentAudioReady) {
          void this.client.startAudioPlayback().catch((retryErr) => {
            retellLog("startAudioPlayback reintento falló", retryErr);
          });
        }
      }, 600);
    });
  }

  private startAudioRetryLoop(): void {
    this.stopAudioRetry();
    let attempts = 0;
    this.audioRetryTimer = window.setInterval(() => {
      if (this.audioPlaybackStarted || this.agentAudioReady) {
        this.ensureAudioPlayback();
        this.stopAudioRetry();
        return;
      }
      attempts += 1;
      if (attempts >= 6) this.stopAudioRetry();
    }, 1000);
  }

  private latestLine(
    lines: Array<{ role?: string; content?: string }>,
    role: "user" | "agent",
  ): string {
    let latest = "";
    for (const entry of lines) {
      const roleRaw = String(entry.role || "").toLowerCase();
      const isUser = roleRaw === "user" || roleRaw === "customer";
      if (role === "user" ? isUser : !isUser) {
        const text = String(entry.content || "").trim();
        if (text) latest = text;
      }
    }
    return latest;
  }

  private emitAgentTranscript(text: string, partial: boolean): void {
    const { text: sttCleaned, incomplete } = sanitizeAgentStt(text);
    const sanitized = sanitizeHudTranscript(sttCleaned);
    if (!sanitized) {
      if (this.currentAgentStreamKey) {
        this.callbacks.onTranscript?.("", "agent", {
          partial: false,
          streamKey: this.currentAgentStreamKey,
        });
      }
      return;
    }
    if (partial) {
      // En vivo: mostrar desde las primeras palabras. Un streamKey estable
      // reescribe la misma burbuja (no cascada).
      if (sanitized.length < 2) return;
    }
    if (!this.currentAgentStreamKey) {
      this.agentTurnSeq += 1;
      this.currentAgentStreamKey = `agent-${this.agentTurnSeq}`;
    }
    this.callbacks.onTranscript?.(sanitized, "agent", {
      partial,
      streamKey: this.currentAgentStreamKey,
      incomplete: incomplete || undefined,
    });
  }

  private setupListeners(): void {
    this.client.on("call_started", () => {
      this.liveKitConnected = true;
      retellLog("call_started — media conectado");
      this.startAudioRetryLoop();
      this.callbacks.onCallStarted?.();
    });

    this.client.on("call_ended", () => {
      retellLog("call_ended");
      this.liveKitConnected = false;
      this.agentAudioReady = false;
      this.audioPlaybackStarted = false;
      this.stopAudioRetry();
      this.clearUserDebounce();
      this.flushUserTranscript(true);
      this.stopLevelLoop();
      this.callbacks.onCallEnded?.();
    });

    this.client.on("call_ready", () => {
      this.agentAudioReady = true;
      retellLog("call_ready — pista agent_audio recibida");
      this.ensureAudioPlayback();
      if (this.levelRaf == null) this.startLevelLoop();
    });

    this.client.on("agent_start_talking", () => {
      this.restoreAgentPlayback();
      this.agentSpeaking = true;
      this.callbacks.onAgentTalking?.(true);
    });

    this.client.on("agent_stop_talking", () => {
      this.agentSpeaking = false;
      this.restoreAgentPlayback();
      this.callbacks.onAgentTalking?.(false);
      if (this.lastAgentLine && this.lastAgentLine !== this.lastPersistedAgentLine) {
        const line = this.lastAgentLine;
        const prev = this.lastPersistedAgentLine;
        if (prev && line.trim().toLowerCase().slice(0, 55) === prev.trim().toLowerCase().slice(0, 55)) {
          // Casi-duplicado de la última línea persistida: no re-emitir.
          // NO reiniciamos el streamKey — Retell envía transcript acumulativo y
          // un mismo turno puede tener varios ciclos start/stop.
          return;
        }
        this.lastPersistedAgentLine = line;
        this.emitAgentTranscript(line, false);
      }
      // El streamKey del agente se mantiene estable durante todo el turno y solo
      // se reinicia al comenzar un nuevo turno del usuario (ver handler "update").
      // Así evitamos la cascada de burbujas creciendo palabra por palabra.
    });

    this.client.on("update", (update: RetellUpdateEvent) => {
      const lines = update.transcript;
      if (!Array.isArray(lines) || lines.length === 0) return;

      const turntaking = update.turntaking;
      if (turntaking === "agent_turn") {
        this.clearUserDebounce();
        const finalUser = this.latestLine(lines, "user");
        if (finalUser) {
          this.pendingUserText = finalUser;
          this.persistUserLine(finalUser);
        }
        // Solo en la transición usuario→agente iniciamos una burbuja nueva.
        // Retell repite "agent_turn" durante todo el turno, así que el guard
        // evita reiniciar el streamKey a mitad de la respuesta (causa de la cascada).
        if (this.lastTurntaking !== "agent_turn") {
          this.currentAgentStreamKey = "";
          this.lastAgentLine = "";
          // No borrar lastPersistedAgentLine: Retell reenvía el turno anterior
          // al empezar el siguiente y eso duplicaba la burbuja en el HUD.
        }
      }
      if (turntaking === "user_turn") {
        this.maybeBargeIn();
      }
      if (turntaking) {
        this.lastTurntaking = turntaking;
      }

      const userText = this.latestLine(lines, "user");
      if (userText && userText !== this.pendingUserText) {
        if (update.turntaking === "user_turn") {
          this.maybeBargeIn();
          this.scheduleUserTranscript(userText);
        }
      }

      const agentText = this.latestLine(lines, "agent");
      if (!agentText || agentText === this.lastAgentLine) return;
      this.lastAgentLine = agentText;
      const now = Date.now();
      const grew = agentText.length - this.lastEmittedAgentPartial.length;
      if (now - this.lastAgentPartialEmitAt < 80 && grew < 6) return;
      this.lastAgentPartialEmitAt = now;
      this.lastEmittedAgentPartial = agentText;
      this.emitAgentTranscript(agentText, true);
    });

    this.client.on("error", (error: unknown) => {
      const raw =
        typeof error === "string"
          ? error
          : error instanceof Error
            ? error.message
            : "Error en llamada Retell";
      const message = mapRetellClientError(raw);
      console.error("[CED:RETELL] error", raw, error);
      this.callbacks.onError?.(message);
    });
  }

  private startLevelLoop(): void {
    this.stopLevelLoop();
    let lastTick = 0;
    const tick = (now: number) => {
      if (now - lastTick >= 120) {
        lastTick = now;
        const analyzer = this.client.analyzerComponent;
        if (analyzer) {
          const level = Math.min(1, Math.max(0, analyzer.calculateVolume()));
          this.callbacks.onAudioLevel?.(level);
        }
      }
      this.levelRaf = window.requestAnimationFrame(tick);
    };
    this.levelRaf = window.requestAnimationFrame(tick);
  }

  private stopLevelLoop(): void {
    if (this.levelRaf != null) {
      window.cancelAnimationFrame(this.levelRaf);
      this.levelRaf = null;
    }
  }

  async startCall(
    accessToken: string,
    callId?: string | null,
    media?: RetellCallMediaOptions,
  ): Promise<void> {
    this.callId = callId ?? null;
    this.lastUserLine = "";
    this.lastAgentLine = "";
    this.lastPersistedAgentLine = "";
    this.lastPersistedUserLine = "";
    this.pendingUserText = "";
    this.clearUserDebounce();
    this.agentAudioReady = false;
    this.liveKitConnected = false;
    this.audioPlaybackStarted = false;
    this.agentSpeaking = false;
    this.agentMutedForBargeIn = false;
    this.agentTurnSeq = 0;
    this.currentAgentStreamKey = "";
    this.lastTurntaking = "";
    this.userTurnSeq = 0;
    this.currentUserStreamKey = "";

    const transport = inferRetellTransport({
      transport: media?.transport,
      accessToken,
      iceServers: media?.ice_servers,
    });
    const config: StartCallConfig = {
      accessToken,
      sampleRate: 24000,
      transport,
      callId: this.callId || undefined,
    };
    if (transport === "gateway") {
      if (media?.ice_servers?.length) config.iceServers = media.ice_servers;
      if (media?.identity) config.identity = media.identity;
    } else if (media?.url) {
      config.url = media.url;
    }
    retellLog("startCall", { callId: this.callId, transport });

    await this.client.startCall(config);
    if (!this.liveKitConnected) {
      throw new Error(mapRetellClientError("Error starting call"));
    }

    window.setTimeout(() => {
      if (!this.agentAudioReady) {
        console.warn(
          "[CED:RETELL] Tras 8s no llegó agent_audio — Revise /v1/retell/call-debug/",
          this.callId,
        );
      }
    }, 8000);
  }

  async stopCall(): Promise<void> {
    this.stopAudioRetry();
    this.clearUserDebounce();
    this.stopLevelLoop();
    this.client.stopCall();
    this.callId = null;
    this.agentAudioReady = false;
    this.liveKitConnected = false;
    this.audioPlaybackStarted = false;
    this.agentSpeaking = false;
    this.agentMutedForBargeIn = false;
    this.youtubeMediaMode = false;
  }

  setMuted(muted: boolean): void {
    if (muted) this.client.mute();
    else this.client.unmute();
  }

  /**
   * Modo media (YouTube) — Opción A:
   * Solo silencia el TTS del agente. El mic sigue activo para mandos por voz
   * (pausa / cierra / siguiente) sin reconectar la llamada.
   */
  setYoutubeMediaMode(active: boolean): void {
    if (this.youtubeMediaMode === active) {
      if (active) this.setAgentTrackVolume(0);
      return;
    }
    this.youtubeMediaMode = active;
    if (active) {
      this.setAgentTrackVolume(0);
      retellLog("youtube media mode ON — solo agent silenciado (mic activo)");
    } else {
      this.setAgentTrackVolume(1);
      retellLog("youtube media mode OFF");
    }
  }

  isYoutubeMediaMode(): boolean {
    return this.youtubeMediaMode;
  }

  getCallId(): string | null {
    return this.callId;
  }
}
