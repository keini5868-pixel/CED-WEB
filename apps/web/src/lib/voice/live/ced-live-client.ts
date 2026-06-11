/**
 * Cliente OpenAI Realtime — misma interfaz que el antiguo CedLiveClient (Gemini).
 */

import type { VoiceSessionPreferences } from "@ced/types";

import { fetchDeepAnalysis, fetchVoiceBrief } from "@/lib/api/openai";
import { fetchEphemeralTokenCached } from "@/lib/voice/ephemeralTokenCache";
import { base64ToArrayBuffer } from "@/lib/audio/pcmUtils";
import { parseCameraIntent } from "@/lib/voice/cameraIntents";
import { cedVoiceError, cedVoiceLog } from "@/lib/voice/cedVoiceLogger";
import {
  BUSCAR_MEMORIA,
  CONSULTAR_SISTEMA_AVANZADO,
  GENERAR_PDF,
  GUARDAR_MEMORIA,
  LIVE_TOOL_NAMES,
} from "@/lib/voice/liveTools";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import { isBenignRealtimeError } from "@/lib/voice/realtimeErrors";
import {
  isInputTranscriptionCompleted,
  isResponseAudioDelta,
  isResponseAudioDone,
  isResponseAudioTranscriptDelta,
} from "@/lib/voice/realtimeEvents";
import { voiceTelemetry } from "@/lib/voice/voiceTelemetry";

const OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime";

const TOOL_ALIAS: Record<string, string> = {
  save_memory: GUARDAR_MEMORIA,
  recall_memory: BUSCAR_MEMORIA,
  generar_pdf: GENERAR_PDF,
  consultar_claude: CONSULTAR_SISTEMA_AVANZADO,
};

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
};

export type CedLiveHandlers = {
  onState?: (state: "connecting" | "connected" | "closed" | "error") => void;
  onSessionReady?: () => void;
  onTranscriptUpdate?: (text: string, role: "user" | "model") => void;
  onTranscript?: (text: string, role: "user" | "model") => void;
  onAudio?: (buffer: ArrayBuffer) => void;
  onTurnComplete?: () => void;
  onModelAudioDone?: () => void;
  onInterrupted?: () => void;
  onSpeechStopped?: () => void;
  onToolStart?: (toolName: string) => void;
  onToolComplete?: () => void;
  onCameraIntent?: (intent: "activate" | "deactivate") => void;
  onError?: (message: string) => void;
  onClose?: (info: GeminiCloseInfo) => void;
  shouldAllowAdvancedTool?: (toolPrompt: string) => boolean;
  onAdvancedToolBlocked?: (toolPrompt: string) => void;
  onLiveTool?: (
    name: string,
    args: Record<string, unknown>,
  ) => Promise<{ spoken?: string } | void>;
};

function classifyOpenAIClose(unexpected: boolean, code: number): GeminiCloseInfo {
  if (!unexpected) {
    return { unexpected: false, recoverable: false };
  }
  const recoverable = code === 1006 || code === 1011 || code >= 4000;
  return {
    unexpected: true,
    recoverable,
    userMessage: recoverable
      ? undefined
      : "OpenAI cerró la sesión. Revisa tu API key y saldo en platform.openai.com.",
    code,
  };
}

export class CedLiveClient {
  private ws: WebSocket | null = null;
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
  private static TOOL_COOLDOWN_MS = 2000;
  private handlers: CedLiveHandlers = {};

  isOpen(): boolean {
    return Boolean(this.ws && this.sessionReady && !this.sendBlocked);
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.sessionReady = false;
    this.sendBlocked = true;
    this.connectGen += 1;
    if (this.ws) {
      try {
        this.ws.close(1000, "client disconnect");
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
    voiceTelemetry.setWsState("disconnected");
    voiceTelemetry.setSessionId(null);
  }

  async connect(
    handlers: CedLiveHandlers,
    options: CedLiveConnectOptions = {},
  ): Promise<boolean> {
    if (this.connectInFlight) return false;

    this.connectInFlight = true;
    this.handlers = handlers;
    this.sendBlocked = true;
    this.disconnect();
    this.intentionalClose = false;
    this.userTranscriptAcc = "";
    this.modelTranscriptAcc = "";
    this.processedCallIds.clear();
    this.recentToolAt.clear();

    const generation = this.connectGen;
    const isStale = () => generation !== this.connectGen;

    handlers.onState?.("connecting");
    voiceTelemetry.reset();
    voiceTelemetry.setWsState("connecting");
    voiceTelemetry.setSessionId(`openai-${Date.now()}`);

    const tokenRes = await fetchEphemeralTokenCached(options.voiceName);
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
    voiceTelemetry.setActiveVoice(voiceName);

    return new Promise<boolean>((resolve) => {
      if (isStale()) {
        this.connectInFlight = false;
        resolve(false);
        return;
      }

      const url = `${OPENAI_REALTIME_URL}?model=${encodeURIComponent(this.model)}`;
      const ws = new WebSocket(url, [
        "realtime",
        `openai-insecure-api-key.${tokenRes.clientSecret}`,
      ]);
      this.ws = ws;

      ws.onopen = () => {
        if (isStale()) return;
        voiceTelemetry.setWsState("connected");
        cedVoiceLog(5, "Conectando OpenAI Realtime", {
          model: this.model,
          voice: voiceName,
        });
      };

      ws.onmessage = (ev) => {
        if (isStale()) return;
        try {
          const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
          void this.handleServerEvent(msg);
        } catch {
          /* ignore */
        }
      };

      ws.onerror = () => {
        if (isStale()) return;
        const msg = "Error en OpenAI Realtime";
        this.sessionReady = false;
        this.sendBlocked = true;
        this.ws = null;
        cedVoiceError("[OPENAI:ERROR]", msg);
        handlers.onState?.("error");
        handlers.onError?.(msg);
        voiceTelemetry.setWsState("error", msg);
        this.connectInFlight = false;
        resolve(false);
      };

      ws.onclose = (event) => {
        if (isStale()) return;
        const unexpected = !this.intentionalClose;
        this.sessionReady = false;
        this.sendBlocked = true;
        this.ws = null;
        voiceTelemetry.setWsState("closed");
        const closeInfo = classifyOpenAIClose(unexpected, event.code);
        handlers.onState?.("closed");
        if (!closeInfo.recoverable && closeInfo.userMessage) {
          handlers.onError?.(closeInfo.userMessage);
          handlers.onState?.("error");
        }
        handlers.onClose?.(closeInfo);
        this.connectInFlight = false;
        if (!this.sessionReady) resolve(false);
      };

      const readyTimeout = window.setTimeout(() => {
        if (!this.sessionReady && !isStale()) {
          handlers.onError?.("OpenAI no respondió a tiempo.");
          handlers.onState?.("error");
          this.connectInFlight = false;
          resolve(false);
        }
      }, 15000);

      const markReady = () => {
        if (this.sessionReady || isStale()) return;
        window.clearTimeout(readyTimeout);
        this.sessionReady = true;
        this.sendBlocked = false;
        voiceTelemetry.markSetupComplete();
        handlers.onState?.("connected");
        handlers.onSessionReady?.();
        cedVoiceLog(6, "OpenAI session ready");
        this.connectInFlight = false;
        resolve(true);
      };

      this.handleServerEvent = async (msg: Record<string, unknown>) => {
        const type = String(msg.type ?? "");

        if (type === "session.created" || type === "session.updated") {
          markReady();
          return;
        }

        if (isResponseAudioDelta(type)) {
          const delta = String(msg.delta ?? "");
          if (delta) {
            voiceTelemetry.markPcmReceived(`pcm16 · ${delta.length}b`);
            handlers.onAudio?.(base64ToArrayBuffer(delta));
          }
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

        if (type === "input_audio_buffer.speech_started") {
          voiceTelemetry.markInterrupted();
          this.userTranscriptAcc = "";
          this.modelTranscriptAcc = "";
          handlers.onInterrupted?.();
          return;
        }

        if (type === "response.done") {
          const response = msg.response as { status?: string } | undefined;
          if (response?.status === "cancelled") {
            cedVoiceLog(5, "OpenAI response cancelled (server VAD)");
          }
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
          const err = msg.error as { message?: string; code?: string } | undefined;
          const message = err?.message ?? "Realtime error";
          if (isBenignRealtimeError(message)) {
            cedVoiceLog(5, "OpenAI benign error ignored", { message });
            return;
          }
          voiceTelemetry.setWsState("error", message);
          handlers.onError?.(message);
        }
      };
    });
  }

  private handleServerEvent: (msg: Record<string, unknown>) => Promise<void> =
    async () => {};

  sendAudioPcm(base64Pcm: string): void {
    if (!this.ws || !base64Pcm || !this.sessionReady || this.sendBlocked) return;
    try {
      this.send({
        type: "input_audio_buffer.append",
        audio: base64Pcm,
      });
      voiceTelemetry.markPcmSent();
    } catch (err) {
      cedVoiceError("sendAudioPcm failed", err);
      this.sessionReady = false;
      this.sendBlocked = true;
      this.ws = null;
    }
  }

  sendVideoJpeg(_base64Jpeg: string): void {
    /* OpenAI Realtime no soporta video uplink — visión vía analyze_camera_frame tool */
  }

  sendAdvancedSystemAck(): void {
    this.sendClientTurn(CED_VOICE_PROFILE_LOCK.advancedSystem.ackInstruction);
  }

  sendSessionGreeting(): void {
    this.sendClientTurn("inicia");
  }

  sendNarrationBrief(summary: string): void {
    const text = summary.trim();
    if (!text) return;
    this.sendClientTurn(`[CED_BRIEF]\n${text}`);
  }

  sendWebSearchAck(): void {
    this.sendClientTurn(CED_VOICE_PROFILE_LOCK.webSearch.ackInstruction);
  }

  private sendClientTurn(text: string): void {
    if (!this.ws || !this.sessionReady || this.sendBlocked) return;
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
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(payload));
  }

  private async dispatchTool(
    rawName: string,
    callId: string,
    args: Record<string, unknown>,
  ): Promise<void> {
    if (!callId || this.processedCallIds.has(callId)) return;
    const dedupeKey = `${rawName}:${JSON.stringify(args)}`;
    const lastAt = this.recentToolAt.get(dedupeKey) ?? 0;
    if (Date.now() - lastAt < CedLiveClient.TOOL_COOLDOWN_MS) return;
    this.recentToolAt.set(dedupeKey, Date.now());
    this.processedCallIds.add(callId);

    const h = this.handlers;
    const name = TOOL_ALIAS[rawName] ?? rawName;

    if (rawName === "search_web") {
      const query = String(args.query ?? "").trim();
      h.onToolStart?.("search_web");
      const brief = await fetchVoiceBrief(query || "noticias hoy", "news");
      const spoken = brief.ok ? brief.summary : "No pude buscar en internet.";
      this.submitToolOutput(callId, { status: "ok", spoken });
      return;
    }

    if (name === CONSULTAR_SISTEMA_AVANZADO) {
      const prompt = String(args.prompt ?? args.query ?? "").trim();
      const allowed = h.shouldAllowAdvancedTool?.(prompt) ?? false;
      if (!allowed) {
        h.onAdvancedToolBlocked?.(prompt);
        this.submitToolOutput(callId, {
          status: "blocked",
          reason: "Requiere confirmación.",
        });
        return;
      }
      h.onToolStart?.(name);
      this.sendAdvancedSystemAck();
      const result = await fetchDeepAnalysis(
        prompt || "consulta general",
        CED_VOICE_PROFILE_LOCK.advancedSystem.fetchTimeoutMs,
      );
      const spoken = result.ok ? result.result : "No pude completar el análisis.";
      this.submitToolOutput(callId, { status: result.ok ? "ok" : "error", spoken });
      return;
    }

    if (LIVE_TOOL_NAMES.has(name) && h.onLiveTool) {
      h.onToolStart?.(name);
      const result = await h.onLiveTool(name, args);
      const spoken = result?.spoken ?? "Listo.";
      this.submitToolOutput(callId, { status: "ok", spoken });
      return;
    }

    this.submitToolOutput(callId, { status: "unknown_tool", name: rawName });
  }

  private submitToolOutput(callId: string, output: Record<string, unknown>): void {
    this.send({
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: callId,
        output: JSON.stringify(output),
      },
    });
    this.send({ type: "response.create" });
  }
}
