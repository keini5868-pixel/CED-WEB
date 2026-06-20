import { RetellWebClient } from "retell-client-js-sdk";

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
    options?: { partial?: boolean },
  ) => void;
  onError?: (message: string) => void;
  onAudioLevel?: (level: number) => void;
}

type RetellUpdateEvent = {
  transcript?: Array<{ role?: string; content?: string }>;
  turntaking?: string;
};

function retellLog(message: string, detail?: unknown): void {
  if (detail !== undefined) {
    console.log(`[CED:RETELL] ${message}`, detail);
  } else {
    console.log(`[CED:RETELL] ${message}`);
  }
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

  constructor() {
    this.client = new RetellWebClient();
    this.setupListeners();
  }

  setCallbacks(callbacks: CedRetellCallbacks): void {
    this.callbacks = callbacks;
  }

  private liveKitRoom(): RetellLiveRoom | undefined {
    return (this.client as unknown as { room?: RetellLiveRoom }).room;
  }

  private muteAgentPlayback(): void {
    try {
      const room = this.liveKitRoom();
      if (!room) return;
      room.remoteParticipants.forEach((participant) => {
        participant.audioTrackPublications.forEach((publication) => {
          if (publication.trackName !== "agent_audio") return;
          publication.track?.setVolume?.(0);
        });
      });      this.agentMutedForBargeIn = true;
      retellLog("barge-in: agent audio silenciado");
    } catch (err) {
      retellLog("barge-in mute falló", err);
    }
  }

  private restoreAgentPlayback(): void {
    if (!this.agentMutedForBargeIn) return;
    try {
      const room = this.liveKitRoom();
      if (!room) return;
      room.remoteParticipants.forEach((participant) => {
        participant.audioTrackPublications.forEach((publication) => {
          if (publication.trackName !== "agent_audio") return;
          publication.track?.setVolume?.(1);
        });
      });      this.agentMutedForBargeIn = false;
    } catch (err) {
      retellLog("barge-in restore falló", err);
    }
  }

  private maybeBargeIn(_userText: string): void {
    // Retell gestiona interrupciones en servidor; silenciar aquí cortaba el audio a medias.
    return;
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
    if (
      this.lastPersistedUserLine &&
      trimmed.startsWith(this.lastPersistedUserLine) &&
      trimmed.length - this.lastPersistedUserLine.length < 4
    ) {
      return;
    }
    this.lastPersistedUserLine = trimmed;
    this.lastUserLine = trimmed;
    this.callbacks.onTranscript?.(trimmed, "user");
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

  private setupListeners(): void {
    this.client.on("call_started", () => {
      this.liveKitConnected = true;
      retellLog("call_started — LiveKit conectado");
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
        this.lastPersistedAgentLine = this.lastAgentLine;
        this.callbacks.onTranscript?.(this.lastAgentLine, "agent", { partial: false });
      }
    });

    this.client.on("update", (update: RetellUpdateEvent) => {
      const lines = update.transcript;
      if (!Array.isArray(lines) || lines.length === 0) return;

      if (update.turntaking === "agent_turn") {
        this.clearUserDebounce();
        const finalUser = this.latestLine(lines, "user");
        if (finalUser) {
          this.pendingUserText = finalUser;
          this.persistUserLine(finalUser);
        }
      }
      if (update.turntaking === "user_turn") {
        this.maybeBargeIn(this.pendingUserText);
      }

      const userText = this.latestLine(lines, "user");
      if (userText && userText !== this.pendingUserText) {
        this.maybeBargeIn(userText);
        if (update.turntaking === "user_turn") {
          this.scheduleUserTranscript(userText);
        }
      }

      const agentText = this.latestLine(lines, "agent");
      if (!agentText || agentText === this.lastAgentLine) return;
      this.lastAgentLine = agentText;
      if (this.agentSpeaking) {
        this.callbacks.onTranscript?.(agentText, "agent", { partial: true });
      }
    });

    this.client.on("error", (error: unknown) => {
      const message =
        typeof error === "string"
          ? error
          : error instanceof Error
            ? error.message
            : "Error en llamada Retell";
      console.error("[CED:RETELL] error", message, error);
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

  async startCall(accessToken: string, callId?: string | null): Promise<void> {
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
    retellLog("startCall", { callId: this.callId });

    await this.client.startCall({
      accessToken,
      sampleRate: 24000,
    });

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
  }

  setMuted(muted: boolean): void {
    if (muted) this.client.mute();
    else this.client.unmute();
  }

  getCallId(): string | null {
    return this.callId;
  }
}
