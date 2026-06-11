/**
 * Captura mic → PCM16 24 kHz (OpenAI Realtime GA).
 * Half-duplex: el hook decide cuándo enviar (no mientras CED habla).
 */

import {
  arrayBufferToBase64,
  resampleInt16,
} from "@/lib/audio/pcmUtils";
import { getAudioContext } from "@/lib/voice/live/audio-context";
import { ensureAudioWorkletModule } from "@/lib/voice/live/worklet-registry";
import AudioRecordingWorklet from "@/lib/voice/live/worklets/audio-recording";

const WORKLET_NAME = "ced-audio-recorder";
export const OPENAI_UPLINK_SAMPLE_RATE = 24000;

export class AudioRecorder {
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private starting: Promise<void> | null = null;
  private onData: ((base64: string) => void) | null = null;
  private shouldSend: (() => boolean) | null = null;
  private captureSampleRate = OPENAI_UPLINK_SAMPLE_RATE;

  setHandlers(handlers: {
    onData: (base64: string) => void;
    shouldSend?: () => boolean;
  }) {
    this.onData = handlers.onData;
    this.shouldSend = handlers.shouldSend ?? (() => true);
  }

  async start(stream: MediaStream): Promise<void> {
    if (this.starting) return this.starting;

    this.starting = (async () => {
      this.cleanupGraph();

      this.stream = stream;
      this.audioContext = await getAudioContext({
        id: "ced-mic",
        sampleRate: OPENAI_UPLINK_SAMPLE_RATE,
        latencyHint: "interactive",
      });
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }
      this.captureSampleRate = this.audioContext.sampleRate;

      await ensureAudioWorkletModule(
        this.audioContext,
        WORKLET_NAME,
        AudioRecordingWorklet,
      );

      this.source = this.audioContext.createMediaStreamSource(stream);
      this.worklet = new AudioWorkletNode(this.audioContext, WORKLET_NAME);
      this.worklet.port.onmessage = (ev: MessageEvent) => {
        const arrayBuffer = ev.data?.data?.int16arrayBuffer as
          | ArrayBuffer
          | undefined;
        if (!arrayBuffer || !this.onData || !this.shouldSend?.()) return;
        const raw = new Int16Array(arrayBuffer);
        const pcm = resampleInt16(
          raw,
          this.captureSampleRate,
          OPENAI_UPLINK_SAMPLE_RATE,
        );
        this.onData(arrayBufferToBase64(pcm.buffer as ArrayBuffer));
      };

      this.source.connect(this.worklet);
      // Mantener el grafo activo sin reproducir al altavoz (evita eco).
      const silent = this.audioContext.createGain();
      silent.gain.value = 0;
      this.worklet.connect(silent);
      silent.connect(this.audioContext.destination);
    })();

    try {
      await this.starting;
    } finally {
      this.starting = null;
    }
  }

  stop() {
    if (this.starting) {
      void this.starting.finally(() => this.cleanupGraph());
      return;
    }
    this.cleanupGraph();
  }

  private cleanupGraph() {
    this.worklet?.port.close();
    this.source?.disconnect();
    this.worklet?.disconnect();
    this.worklet = null;
    this.source = null;
    this.stream = null;
  }
}
