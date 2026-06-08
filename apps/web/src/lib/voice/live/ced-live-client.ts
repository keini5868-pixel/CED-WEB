/**
 * Cliente Gemini Live — capa fina sobre @google/genai (patrón live-api-web-console).
 */

import type { LiveServerMessage } from "@google/genai";
import { GoogleGenAI } from "@google/genai";

import type { VoiceSessionPreferences } from "@ced/types";

import { fetchDeepAnalysis } from "@/lib/api/gemini";
import { fetchEphemeralTokenCached } from "@/lib/voice/ephemeralTokenCache";
import { base64ToArrayBuffer } from "@/lib/audio/pcmUtils";
import { buildLiveConfig } from "@/lib/voice/live/build-live-config";
import { parseCameraIntent } from "@/lib/voice/cameraIntents";
import {
  classifyGeminiClose,
  type GeminiCloseInfo,
} from "@/lib/voice/geminiCloseErrors";
import { cedVoiceError, cedVoiceLog } from "@/lib/voice/cedVoiceLogger";
import {
  extractAudioParts,
  extractModelText,
} from "@/lib/voice/geminiMessageParser";
import {
  CONSULTAR_SISTEMA_AVANZADO,
  LIVE_TOOL_NAMES,
} from "@/lib/voice/liveTools";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import { mergeTranscriptChunk } from "@/lib/voice/transcriptAccumulator";
import { voiceTelemetry } from "@/lib/voice/voiceTelemetry";

type LiveSession = {
  close: () => void;
  sendRealtimeInput: (params: {
    audio?: { data: string; mimeType: string };
    video?: { data: string; mimeType: string };
    text?: string;
  }) => void;
  sendClientContent: (params: { turns?: string; turnComplete?: boolean }) => void;
  sendToolResponse: (params: {
    functionResponses:
      | { id?: string; name?: string; response: Record<string, unknown> }
      | Array<{ id?: string; name?: string; response: Record<string, unknown> }>;
  }) => void;
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
  onInterrupted?: () => void;
  onToolStart?: (toolName: string) => void;
  onToolComplete?: () => void;
  onCameraIntent?: (intent: "activate" | "deactivate") => void;
  onError?: (message: string) => void;
  onClose?: (info: GeminiCloseInfo) => void;
  /** false = bloquear consultar_sistema_avanzado (sin confirmación o es búsqueda web). */
  shouldAllowAdvancedTool?: (toolPrompt: string) => boolean;
  /** Herramienta bloqueada — redirigir a búsqueda web si aplica. */
  onAdvancedToolBlocked?: (toolPrompt: string) => void;
  /** Herramientas Live custom (memoria, prospección, visión). */
  onLiveTool?: (
    name: string,
    args: Record<string, unknown>,
  ) => Promise<{ spoken?: string } | void>;
};

export class CedLiveClient {
  private session: LiveSession | null = null;
  private sessionReady = false;
  private connectGen = 0;
  private connectInFlight = false;
  private intentionalClose = false;
  private sendBlocked = true;
  private userTranscriptAcc = "";
  private modelTranscriptAcc = "";
  private processedToolIds = new Set<string>();
  private recentToolAt = new Map<string, number>();
  private static TOOL_COOLDOWN_MS = 2000;
  private handlers: CedLiveHandlers = {};
  private turnCompletePending = false;
  private turnCompleteTimer: ReturnType<typeof setTimeout> | null = null;

  isOpen(): boolean {
    return Boolean(this.session && this.sessionReady && !this.sendBlocked);
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.sessionReady = false;
    this.sendBlocked = true;
    this.connectGen += 1;
    this.clearTurnCompleteTimer();
    const sess = this.session;
    this.session = null;
    try {
      sess?.close();
    } catch {
      /* ignore */
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
    this.processedToolIds.clear();
    this.recentToolAt.clear();

    const generation = this.connectGen;
    const isStale = () => generation !== this.connectGen;

    handlers.onState?.("connecting");
    voiceTelemetry.reset();
    voiceTelemetry.setWsState("connecting");
    voiceTelemetry.setSessionId(`live-${Date.now()}`);

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

    const voiceName = tokenRes.voiceName ?? "Charon";
    voiceTelemetry.setActiveVoice(voiceName);

    try {
      const ai = new GoogleGenAI({
        apiKey: tokenRes.token,
        httpOptions: { apiVersion: "v1alpha" },
      });

      if (isStale()) {
        this.connectInFlight = false;
        return false;
      }

      const config = buildLiveConfig({
        systemInstruction: tokenRes.systemInstruction,
        voiceName,
        language: options.language ?? "es",
        responseSpeed: options.responseSpeed ?? "fast",
      });

      cedVoiceLog(5, "Conectando Gemini Live", {
        model: tokenRes.model,
        voice: voiceName,
      });

      const session = await ai.live.connect({
        model: tokenRes.model,
        config,
        callbacks: {
          onopen: () => {
            if (isStale()) return;
            voiceTelemetry.setWsState("connected");
          },
          onmessage: (message: LiveServerMessage) => {
            if (isStale()) return;
            this.handleMessage(message);
          },
          onerror: (e: ErrorEvent) => {
            if (isStale()) return;
            const msg = e.message || "Error en Gemini Live";
            this.sessionReady = false;
            this.sendBlocked = true;
            this.session = null;
            cedVoiceError("[GEMINI:ERROR]", msg);
            handlers.onState?.("error");
            handlers.onError?.(msg);
            voiceTelemetry.setWsState("error", msg);
          },
          onclose: (event: CloseEvent) => {
            if (isStale()) return;
            const unexpected = !this.intentionalClose;
            this.sessionReady = false;
            this.sendBlocked = true;
            this.session = null;
            voiceTelemetry.setWsState("closed");
            const closeInfo = classifyGeminiClose(unexpected, event);
            handlers.onState?.("closed");
            if (!closeInfo.recoverable && closeInfo.userMessage) {
              handlers.onError?.(closeInfo.userMessage);
              handlers.onState?.("error");
            }
            handlers.onClose?.(closeInfo);
          },
        },
      });

      if (isStale()) {
        try {
          session.close();
        } catch {
          /* ignore */
        }
        this.connectInFlight = false;
        return false;
      }

      this.session = session as LiveSession;
      this.connectInFlight = false;
      return true;
    } catch (err) {
      if (!isStale()) {
        const msg =
          err instanceof Error ? err.message : "No se pudo conectar a Gemini Live";
        handlers.onState?.("error");
        handlers.onError?.(msg);
        voiceTelemetry.setWsState("error", msg);
      }
      this.connectInFlight = false;
      return false;
    }
  }

  sendAudioPcm(base64Pcm: string): void {
    if (!this.session || !base64Pcm || !this.sessionReady || this.sendBlocked) {
      return;
    }
    try {
      this.session.sendRealtimeInput({
        audio: { data: base64Pcm, mimeType: "audio/pcm;rate=16000" },
      });
      voiceTelemetry.markPcmSent();
    } catch (err) {
      cedVoiceError("sendAudioPcm failed", err);
      this.sessionReady = false;
      this.sendBlocked = true;
      this.session = null;
    }
  }

  sendVideoJpeg(base64Jpeg: string): void {
    if (!this.session || !this.sessionReady || this.sendBlocked) return;
    const payload = base64Jpeg.includes(",")
      ? base64Jpeg.split(",")[1]!
      : base64Jpeg;
    try {
      this.session.sendRealtimeInput({
        video: { data: payload, mimeType: "image/jpeg" },
      });
    } catch (err) {
      cedVoiceError("sendVideoJpeg failed", err);
    }
  }

  /** ACK mientras el backend consulta al sistema avanzado. */
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

  /** ACK corto mientras el backend busca en internet. */
  sendWebSearchAck(): void {
    this.sendClientTurn(CED_VOICE_PROFILE_LOCK.webSearch.ackInstruction);
  }

  private sendClientTurn(turns: string): void {
    if (!this.session || !this.sessionReady || this.sendBlocked) return;
    try {
      this.session.sendClientContent({ turns, turnComplete: true });
    } catch (err) {
      cedVoiceError("sendClientContent failed", err);
    }
  }

  private handleMessage(message: LiveServerMessage): void {
    const h = this.handlers;

    if (message.setupComplete && !this.sessionReady) {
      this.sessionReady = true;
      this.sendBlocked = false;
      voiceTelemetry.markSetupComplete();
      h.onState?.("connected");
      h.onSessionReady?.();
      cedVoiceLog(6, "Gemini setupComplete");
    }

    if (message.toolCall) {
      this.dispatchToolCall(message.toolCall);
    }
    if (message.toolCallCancellation) {
      h.onToolComplete?.();
    }

    const inputText = message.serverContent?.inputTranscription?.text;
    if (inputText && !/^<noise>$/i.test(inputText.trim())) {
      this.userTranscriptAcc = mergeTranscriptChunk(
        this.userTranscriptAcc,
        inputText,
      );
      voiceTelemetry.markUserTranscript(this.userTranscriptAcc);
      h.onTranscriptUpdate?.(this.userTranscriptAcc, "user");
    }

    const outputText = message.serverContent?.outputTranscription?.text;
    if (outputText) {
      this.modelTranscriptAcc = mergeTranscriptChunk(
        this.modelTranscriptAcc,
        outputText,
      );
      h.onTranscriptUpdate?.(this.modelTranscriptAcc, "model");
    }

    const modelText = extractModelText(message);
    if (modelText) {
      this.modelTranscriptAcc = mergeTranscriptChunk(
        this.modelTranscriptAcc,
        modelText,
      );
      h.onTranscriptUpdate?.(this.modelTranscriptAcc, "model");
    }

    const audioParts = extractAudioParts(message);
    for (const audio of audioParts) {
      voiceTelemetry.markPcmReceived(`${audio.mimeType} · ${audio.data.length}b`);
      const buffer = base64ToArrayBuffer(audio.data);
      h.onAudio?.(buffer);
    }
    if (audioParts.length > 0 && this.turnCompletePending) {
      this.scheduleTurnComplete();
    }

    if (message.serverContent?.interrupted) {
      this.clearTurnCompleteTimer();
      voiceTelemetry.markInterrupted();
      this.userTranscriptAcc = "";
      this.modelTranscriptAcc = "";
      this.processedToolIds.clear();
      this.recentToolAt.clear();
      h.onInterrupted?.();
    }

    if (message.serverContent?.turnComplete) {
      this.turnCompletePending = true;
      this.scheduleTurnComplete();
    }
  }

  private clearTurnCompleteTimer() {
    this.turnCompletePending = false;
    if (this.turnCompleteTimer) {
      clearTimeout(this.turnCompleteTimer);
      this.turnCompleteTimer = null;
    }
  }

  private scheduleTurnComplete() {
    if (this.turnCompleteTimer) clearTimeout(this.turnCompleteTimer);
    this.turnCompleteTimer = setTimeout(() => {
      this.turnCompleteTimer = null;
      if (!this.turnCompletePending) return;
      this.turnCompletePending = false;
      this.finalizeTurn();
    }, CED_VOICE_PROFILE_LOCK.live.turnCompleteDelayMs);
  }

  private finalizeTurn() {
    const h = this.handlers;
    if (this.userTranscriptAcc.trim()) {
      const finalUser = this.userTranscriptAcc.trim();
      h.onTranscript?.(finalUser, "user");
      const intent = parseCameraIntent(finalUser);
      if (intent) h.onCameraIntent?.(intent);
      this.userTranscriptAcc = "";
    }
    if (this.modelTranscriptAcc.trim()) {
      h.onTranscript?.(this.modelTranscriptAcc.trim(), "model");
      this.modelTranscriptAcc = "";
    }
    voiceTelemetry.markTurnComplete();
    h.onTurnComplete?.();
  }

  private dispatchToolCall(toolCall: {
    functionCalls?: Array<{
      id?: string;
      name?: string;
      args?: Record<string, unknown>;
    }>;
  }): void {
    const calls = toolCall.functionCalls ?? [];
    const pending = calls.filter((call) => {
      const name = call.name ?? "";
      if (name === "google_search" || name === "googleSearch") return false;
      if (!LIVE_TOOL_NAMES.has(name)) return false;
      const id = call.id ?? `${name}:${JSON.stringify(call.args)}`;
      if (this.processedToolIds.has(id)) return false;
      const dedupeKey = `${name}:${JSON.stringify(call.args ?? {})}`;
      const lastAt = this.recentToolAt.get(dedupeKey) ?? 0;
      if (Date.now() - lastAt < CedLiveClient.TOOL_COOLDOWN_MS) return false;
      this.recentToolAt.set(dedupeKey, Date.now());
      this.processedToolIds.add(id);
      return true;
    });
    if (!pending.length) return;

    void (async () => {
      const responses: Array<{
        id?: string;
        name?: string;
        response: Record<string, unknown>;
      }> = [];

      for (const call of pending) {
        const name = call.name ?? "";
        const args = call.args ?? {};

        if (name === CONSULTAR_SISTEMA_AVANZADO) {
          const prompt = String(args.prompt ?? "").trim();
          const allowed = this.handlers.shouldAllowAdvancedTool?.(prompt) ?? false;

          if (!allowed) {
            this.handlers.onAdvancedToolBlocked?.(prompt);
            responses.push({
              id: call.id,
              name: call.name,
              response: {
                status: "blocked",
                reason: "Requiere confirmación o no aplica.",
              },
            });
            continue;
          }

          this.handlers.onToolStart?.(name);
          this.sendAdvancedSystemAck();
          const result = await fetchDeepAnalysis(
            prompt || "consulta general",
            CED_VOICE_PROFILE_LOCK.advancedSystem.fetchTimeoutMs,
          );
          const spoken = result.ok
            ? result.result.slice(
                0,
                CED_VOICE_PROFILE_LOCK.advancedSystem.maxSpokenChars,
              )
            : `No pude completar la consulta: ${result.error}`;
          responses.push({ id: call.id, name: call.name, response: { status: "ok" } });
          if (spoken && this.session && this.sessionReady && !this.sendBlocked) {
            window.setTimeout(() => {
              if (!this.session || !this.sessionReady || this.sendBlocked) return;
              this.sendNarrationBrief(spoken);
            }, 120);
          }
          continue;
        }

        this.handlers.onToolStart?.(name);
        cedVoiceLog(5, "Live tool", { name });
        let spoken: string | undefined;
        try {
          const out = await this.handlers.onLiveTool?.(name, args);
          spoken = out?.spoken;
        } catch (err) {
          cedVoiceError(`tool ${name} failed`, err);
          spoken = "Hubo un error al ejecutar la herramienta.";
        }
        responses.push({
          id: call.id,
          name: call.name,
          response: {
            status: spoken ? "ok" : "error",
            summary: spoken || "No se pudo completar.",
          },
        });
        continue;
      }

      if (responses.length && this.session && this.sessionReady && !this.sendBlocked) {
        try {
          this.session.sendToolResponse({ functionResponses: responses });
        } catch (err) {
          cedVoiceError("sendToolResponse failed", err);
        }
      }
      this.handlers.onToolComplete?.();
    })();
  }
}
