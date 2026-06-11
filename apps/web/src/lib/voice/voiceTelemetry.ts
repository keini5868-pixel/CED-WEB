/** Telemetría en vivo del pipeline Gemini Live (dev / debug). */

import { isBenignRealtimeError } from "@/lib/voice/realtimeErrors";

export type WsState = "disconnected" | "connecting" | "connected" | "closed" | "error";

export type VoiceTurnLogEntry = {
  id: string;
  at: number;
  kind:
    | "ws_open"
    | "ws_close"
    | "ws_error"
    | "setup_complete"
    | "pcm_sent"
    | "pcm_recv"
    | "user_transcript"
    | "user_speech_end"
    | "model_audio"
    | "audio_played"
    | "turn_complete"
    | "interrupted"
    | "voice_change"
    | "session_connect"
    | "session_disconnect";
  detail?: string;
  latencyMs?: number;
};

export type VoiceTelemetrySnapshot = {
  wsState: WsState;
  sessionId: string | null;
  activeVoice: string;
  captureFormat: string;
  captureEngine: string;
  inputSampleRate: number;
  chunkMs: number;
  chunksSent: number;
  chunksReceived: number;
  chunksSentPerSec: number;
  chunksRecvPerSec: number;
  messagesSent: number;
  messagesReceived: number;
  lastLatencyMs: number | null;
  avgLatencyMs: number | null;
  networkLatencyMs: number | null;
  playbackLatencyMs: number | null;
  e2eLatencyMs: number | null;
  pipelineQueueMs: number | null;
  pipelineUnderruns: number;
  pipelinePacketGapMs: number | null;
  lastError: string | null;
  turnLogs: VoiceTurnLogEntry[];
};

type Listener = () => void;

const MAX_LOGS = 50;
const LATENCY_WINDOW = 16;

let idSeq = 0;

function nextId() {
  idSeq += 1;
  return `v${idSeq}`;
}

class VoiceTelemetryStore {
  private listeners = new Set<Listener>();

  wsState: WsState = "disconnected";
  sessionId: string | null = null;
  activeVoice = "Aoede";
  captureFormat = "24 kHz · PCM16 · mono";
  captureEngine = "AudioWorklet";
  inputSampleRate = 24000;
  chunkMs = 30;
  chunksSent = 0;
  chunksReceived = 0;
  messagesSent = 0;
  messagesReceived = 0;
  lastLatencyMs: number | null = null;
  networkLatencyMs: number | null = null;
  playbackLatencyMs: number | null = null;
  e2eLatencyMs: number | null = null;
  pipelineQueueMs: number | null = null;
  pipelineUnderruns = 0;
  pipelinePacketGapMs: number | null = null;
  lastError: string | null = null;
  turnLogs: VoiceTurnLogEntry[] = [];
  private latencySamples: number[] = [];
  private sentTimestamps: number[] = [];
  private recvTimestamps: number[] = [];
  private userSpeechEndAt: number | null = null;
  private firstAudioReceivedAt: number | null = null;
  private awaitingResponse = false;

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private notify() {
    for (const fn of this.listeners) fn();
  }

  reset() {
    this.wsState = "disconnected";
    this.sessionId = null;
    this.chunksSent = 0;
    this.chunksReceived = 0;
    this.messagesSent = 0;
    this.messagesReceived = 0;
    this.lastLatencyMs = null;
    this.networkLatencyMs = null;
    this.playbackLatencyMs = null;
    this.e2eLatencyMs = null;
    this.pipelineQueueMs = null;
    this.pipelineUnderruns = 0;
    this.pipelinePacketGapMs = null;
    this.lastError = null;
    this.turnLogs = [];
    this.latencySamples = [];
    this.sentTimestamps = [];
    this.recvTimestamps = [];
    this.userSpeechEndAt = null;
    this.firstAudioReceivedAt = null;
    this.awaitingResponse = false;
    this.notify();
  }

  setActiveVoice(voice: string) {
    this.activeVoice = voice;
    this.notify();
  }

  setCaptureMeta(engine: string, sampleRate: number, chunkMs: number) {
    this.captureEngine = engine;
    this.inputSampleRate = sampleRate;
    this.chunkMs = chunkMs;
    this.notify();
  }

  setWsState(state: WsState, detail?: string) {
    this.wsState = state;
    if (state === "error" && detail && !isBenignRealtimeError(detail)) {
      this.lastError = detail;
    }
    const kind =
      state === "connecting"
        ? "session_connect"
        : state === "closed"
          ? "ws_close"
          : state === "error"
            ? "ws_error"
            : "ws_open";
    this.pushLog(kind, detail);
  }

  setSessionId(id: string | null) {
    this.sessionId = id;
    this.notify();
  }

  markVoiceChange(voice: string) {
    this.activeVoice = voice;
    this.pushLog("voice_change", voice);
    this.notify();
  }

  markSetupComplete() {
    this.pushLog("setup_complete", "Gemini listo para PCM");
  }

  markPcmSent() {
    const now = performance.now();
    this.chunksSent += 1;
    this.messagesSent += 1;
    this.sentTimestamps.push(now);
    this.trimTimestamps(this.sentTimestamps);
    this.notify();
  }

  markPcmReceived(detail?: string) {
    const now = performance.now();
    this.chunksReceived += 1;
    this.messagesReceived += 1;
    this.recvTimestamps.push(now);
    this.trimTimestamps(this.recvTimestamps);

    if (this.awaitingResponse && this.userSpeechEndAt && !this.firstAudioReceivedAt) {
      this.firstAudioReceivedAt = now;
      this.networkLatencyMs = Math.round(now - this.userSpeechEndAt);
      this.pushLog("model_audio", detail, this.networkLatencyMs);
    } else {
      this.pushLog("model_audio", detail);
    }
    this.notify();
  }

  markFirstAudioPlayed() {
    const now = performance.now();
    if (!this.userSpeechEndAt) return;

    const e2e = Math.round(now - this.userSpeechEndAt);
    this.e2eLatencyMs = e2e;
    this.lastLatencyMs = e2e;
    this.latencySamples.push(e2e);
    if (this.latencySamples.length > LATENCY_WINDOW) this.latencySamples.shift();

    if (this.firstAudioReceivedAt) {
      this.playbackLatencyMs = Math.round(now - this.firstAudioReceivedAt);
    }

    this.awaitingResponse = false;
    this.pushLog("audio_played", "primer chunk audible", e2e);
    this.notify();
  }

  markUserTranscript(text: string) {
    this.pushLog("user_transcript", text.slice(0, 120));
    this.notify();
  }

  markUserSpeechEnd() {
    this.userSpeechEndAt = performance.now();
    this.firstAudioReceivedAt = null;
    this.networkLatencyMs = null;
    this.playbackLatencyMs = null;
    this.e2eLatencyMs = null;
    this.awaitingResponse = true;
    this.pushLog("user_speech_end", "silencio detectado");
    this.notify();
  }

  markTurnComplete() {
    this.pushLog("turn_complete");
    this.awaitingResponse = false;
    this.notify();
  }

  markInterrupted() {
    this.pushLog("interrupted", "barge-in");
    this.firstAudioReceivedAt = null;
    this.notify();
  }

  setPipelineStats(stats: {
    queueMs: number;
    underrunCount: number;
    lastPacketGapMs: number | null;
  }) {
    this.pipelineQueueMs = stats.queueMs;
    this.pipelineUnderruns = stats.underrunCount;
    this.pipelinePacketGapMs = stats.lastPacketGapMs;
    this.notify();
  }

  private pushLog(
    kind: VoiceTurnLogEntry["kind"],
    detail?: string,
    latencyMs?: number,
  ) {
    this.turnLogs.unshift({
      id: nextId(),
      at: Date.now(),
      kind,
      detail,
      latencyMs,
    });
    if (this.turnLogs.length > MAX_LOGS) {
      this.turnLogs.length = MAX_LOGS;
    }
  }

  private trimTimestamps(arr: number[]) {
    const cutoff = performance.now() - 1000;
    while (arr.length > 0 && (arr[0] ?? 0) < cutoff) arr.shift();
  }

  getSnapshot(): VoiceTelemetrySnapshot {
    const avg =
      this.latencySamples.length > 0
        ? Math.round(
            this.latencySamples.reduce((a, b) => a + b, 0) /
              this.latencySamples.length,
          )
        : null;
    return {
      wsState: this.wsState,
      sessionId: this.sessionId,
      activeVoice: this.activeVoice,
      captureFormat: this.captureFormat,
      captureEngine: this.captureEngine,
      inputSampleRate: this.inputSampleRate,
      chunkMs: this.chunkMs,
      chunksSent: this.chunksSent,
      chunksReceived: this.chunksReceived,
      chunksSentPerSec: this.sentTimestamps.length,
      chunksRecvPerSec: this.recvTimestamps.length,
      messagesSent: this.messagesSent,
      messagesReceived: this.messagesReceived,
      lastLatencyMs: this.lastLatencyMs,
      avgLatencyMs: avg,
      networkLatencyMs: this.networkLatencyMs,
      playbackLatencyMs: this.playbackLatencyMs,
      e2eLatencyMs: this.e2eLatencyMs,
      pipelineQueueMs: this.pipelineQueueMs,
      pipelineUnderruns: this.pipelineUnderruns,
      pipelinePacketGapMs: this.pipelinePacketGapMs,
      lastError: this.lastError,
      turnLogs: [...this.turnLogs],
    };
  }
}

export const voiceTelemetry = new VoiceTelemetryStore();

export function isVoiceDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  if (process.env.NODE_ENV === "development") return true;
  return window.localStorage.getItem("CED_DEBUG_VOICE") === "1";
}
