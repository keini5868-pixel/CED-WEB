/**
 * Captura mic → PCM16 16 kHz vía worklet inline.
 * @see https://github.com/google-gemini/live-api-web-console
 */

import {
  arrayBufferToBase64,
  downsampleInt16To16k,
} from "@/lib/audio/pcmUtils";
import { getAudioContext } from "@/lib/voice/live/audio-context";
import { createWorkletFromSrc } from "@/lib/voice/live/worklet-loader";
import AudioRecordingWorklet from "@/lib/voice/live/worklets/audio-recording";

const WORKLET_NAME = "ced-audio-recorder";

export class AudioRecorder {
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private starting: Promise<void> | null = null;
  private onData: ((base64: string) => void) | null = null;
  private shouldSend: (() => boolean) | null = null;
  private captureSampleRate = 16000;

  setHandlers(handlers: {
    onData: (base64: string) => void;
    shouldSend?: () => boolean;
  }) {
    this.onData = handlers.onData;
    this.shouldSend = handlers.shouldSend ?? (() => true);
  }

  async start(stream: MediaStream): Promise<void> {
    if (this.starting) return this.starting;

    this.starting = new Promise<void>(async (resolve, reject) => {
      try {
        this.stream = stream;
        this.audioContext = await getAudioContext({
          id: "ced-mic",
          sampleRate: 16000,
          latencyHint: "interactive",
        });
        if (this.audioContext.state === "suspended") {
          await this.audioContext.resume();
        }
        this.captureSampleRate = this.audioContext.sampleRate;

        this.source = this.audioContext.createMediaStreamSource(stream);
        const src = createWorkletFromSrc(WORKLET_NAME, AudioRecordingWorklet);
        await this.audioContext.audioWorklet.addModule(src);
        URL.revokeObjectURL(src);

        this.worklet = new AudioWorkletNode(this.audioContext, WORKLET_NAME);
        this.worklet.port.onmessage = (ev: MessageEvent) => {
          const arrayBuffer = ev.data?.data?.int16arrayBuffer as
            | ArrayBuffer
            | undefined;
          if (!arrayBuffer || !this.onData || !this.shouldSend?.()) return;
          const raw = new Int16Array(arrayBuffer);
          const pcm =
            this.captureSampleRate > 16000
              ? downsampleInt16To16k(raw, this.captureSampleRate)
              : raw;
          this.onData(arrayBufferToBase64(pcm.buffer as ArrayBuffer));
        };

        this.source.connect(this.worklet);
        const mute = this.audioContext.createGain();
        mute.gain.value = 0;
        this.worklet.connect(mute);
        mute.connect(this.audioContext.destination);

        resolve();
      } catch (err) {
        reject(err);
      } finally {
        this.starting = null;
      }
    });

    return this.starting;
  }

  stop() {
    const cleanup = () => {
      this.source?.disconnect();
      this.worklet?.disconnect();
      this.worklet = null;
      this.source = null;
      this.audioContext = null;
      this.stream = null;
    };
    if (this.starting) {
      void this.starting.then(cleanup);
      return;
    }
    cleanup();
  }
}
