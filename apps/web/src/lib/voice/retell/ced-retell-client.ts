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
  private audioRetryTimer: number | null = null;
  private agentAudioReady = false;

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

  /** Retell/LiveKit requiere desbloqueo de audio tras gesto del usuario. */
  private ensureAudioPlayback(): void {
    void this.client.startAudioPlayback().catch((err) => {
      retellLog("startAudioPlayback falló", err);
    });
  }

  private startAudioRetryLoop(): void {
    this.stopAudioRetry();
    let attempts = 0;
    this.ensureAudioPlayback();
    this.audioRetryTimer = window.setInterval(() => {
      attempts += 1;
      this.ensureAudioPlayback();
      if (attempts >= 12) this.stopAudioRetry();
    }, 500);
  }

  private setupListeners(): void {
    this.client.on("call_started", () => {
      retellLog("call_started — LiveKit conectado");
      this.startAudioRetryLoop();
      this.callbacks.onCallStarted?.();
    });

    this.client.on("call_ended", () => {
      retellLog("call_ended");
      this.agentAudioReady = false;
      this.stopAudioRetry();
      this.stopLevelLoop();
      this.callbacks.onCallEnded?.();
    });

    this.client.on("call_ready", () => {
      this.agentAudioReady = true;
      retellLog("call_ready — pista agent_audio recibida (Retell va a hablar)");
      this.ensureAudioPlayback();
    });

    this.client.on("agent_start_talking", () => {
      retellLog("agent_start_talking");
      this.ensureAudioPlayback();
      this.callbacks.onAgentTalking?.(true);
    });

    this.client.on("agent_stop_talking", () => {
      retellLog("agent_stop_talking");
      this.callbacks.onAgentTalking?.(false);
    });

    this.client.on("update", (update: RetellUpdateEvent) => {
      const lines = update.transcript;
      if (!Array.isArray(lines) || lines.length === 0) return;

      for (const entry of lines) {
        const roleRaw = String(entry.role || "").toLowerCase();
        const text = String(entry.content || "").trim();
        if (!text) continue;
        const role: RetellTranscriptRole =
          roleRaw === "user" || roleRaw === "customer" ? "user" : "agent";

        if (role === "user") {
          if (text === this.lastUserLine) continue;
          this.lastUserLine = text;
        } else {
          if (text === this.lastAgentLine) continue;
          this.lastAgentLine = text;
          retellLog("transcript agente", text);
          this.ensureAudioPlayback();
        }
        this.callbacks.onTranscript?.(text, role);
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
    const tick = () => {
      const analyzer = this.client.analyzerComponent;
      if (analyzer) {
        const level = Math.min(1, Math.max(0, analyzer.calculateVolume()));
        this.callbacks.onAudioLevel?.(level);
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
    this.agentAudioReady = false;
    retellLog("startCall", { callId: this.callId });
    this.ensureAudioPlayback();
    await this.client.startCall({
      accessToken,
      sampleRate: 24000,
    });
    this.startLevelLoop();
    this.startAudioRetryLoop();

    window.setTimeout(() => {
      if (!this.agentAudioReady) {
        console.warn(
          "[CED:RETELL] Tras 8s no llegó agent_audio — Retell no generó voz. Revise /v1/retell/call-debug/",
          this.callId,
        );
      }
    }, 8000);
  }

  async stopCall(): Promise<void> {
    this.stopAudioRetry();
    this.stopLevelLoop();
    this.client.stopCall();
    this.callId = null;
    this.agentAudioReady = false;
  }

  setMuted(muted: boolean): void {
    if (muted) this.client.mute();
    else this.client.unmute();
  }

  getCallId(): string | null {
    return this.callId;
  }
}
