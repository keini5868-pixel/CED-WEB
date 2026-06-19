import { RetellWebClient } from "retell-client-js-sdk";

export type RetellTranscriptRole = "user" | "agent";

export interface CedRetellCallbacks {
  onCallStarted?: () => void;
  onCallEnded?: () => void;
  onAgentTalking?: (talking: boolean) => void;
  onTranscript?: (text: string, role: RetellTranscriptRole) => void;
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

  constructor() {
    this.client = new RetellWebClient();
    this.setupListeners();
  }

  setCallbacks(callbacks: CedRetellCallbacks): void {
    this.callbacks = callbacks;
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
    if (text === this.lastPersistedUserLine) return;
    this.lastPersistedUserLine = text;
    this.lastUserLine = text;
    this.callbacks.onTranscript?.(text, "user");
  }

  private scheduleUserTranscript(text: string): void {
    if (text === this.lastPersistedUserLine || text === this.pendingUserText) return;
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
      retellLog("startAudioPlayback falló", err);
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
      this.flushUserTranscript(true);
      this.callbacks.onAgentTalking?.(true);
    });

    this.client.on("agent_stop_talking", () => {
      this.callbacks.onAgentTalking?.(false);
      if (this.lastAgentLine && this.lastAgentLine !== this.lastPersistedAgentLine) {
        this.lastPersistedAgentLine = this.lastAgentLine;
        this.callbacks.onTranscript?.(this.lastAgentLine, "agent");
      }
    });

    this.client.on("update", (update: RetellUpdateEvent) => {
      const lines = update.transcript;
      if (!Array.isArray(lines) || lines.length === 0) return;

      if (update.turntaking === "agent_turn") {
        this.flushUserTranscript(true);
      }

      const userText = this.latestLine(lines, "user");
      if (userText && userText !== this.pendingUserText) {
        this.scheduleUserTranscript(userText);
      }

      const agentText = this.latestLine(lines, "agent");
      if (!agentText || agentText === this.lastAgentLine) return;
      this.lastAgentLine = agentText;
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
  }

  setMuted(muted: boolean): void {
    if (muted) this.client.mute();
    else this.client.unmute();
  }

  getCallId(): string | null {
    return this.callId;
  }
}
