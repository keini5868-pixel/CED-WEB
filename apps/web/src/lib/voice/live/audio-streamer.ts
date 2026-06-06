/**
 * Playback Gemini 24 kHz — AudioBufferSourceNode programado (Google live-api-web-console).
 * Una sola línea de tiempo: no reiniciar scheduledTime entre chunks.
 */

export class AudioStreamer {
  private sampleRate = 24000;
  private bufferSize = 7680;
  private audioQueue: Float32Array[] = [];
  private isPlaying = false;
  private isStreamComplete = false;
  private checkInterval: ReturnType<typeof setInterval> | null = null;
  private scheduledTime = 0;
  private initialBufferTime = 0.1;
  private gainNode: GainNode;
  private endOfQueueSource: AudioBufferSourceNode | null = null;
  private activeSources = new Set<AudioBufferSourceNode>();
  onComplete = () => {};

  constructor(public context: AudioContext) {
    this.gainNode = this.context.createGain();
    this.gainNode.connect(this.context.destination);
  }

  async warmup(): Promise<void> {
    if (this.context.state === "suspended") {
      await this.context.resume();
    }
  }

  private processPcm16Chunk(chunk: Uint8Array): Float32Array {
    const float32 = new Float32Array(chunk.length / 2);
    const view = new DataView(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    for (let i = 0; i < float32.length; i++) {
      float32[i] = view.getInt16(i * 2, true) / 32768;
    }
    return float32;
  }

  addPCM16(chunk: Uint8Array) {
    this.isStreamComplete = false;
    let processing = this.processPcm16Chunk(chunk);
    while (processing.length >= this.bufferSize) {
      this.audioQueue.push(processing.slice(0, this.bufferSize));
      processing = processing.slice(this.bufferSize);
    }
    if (processing.length > 0) {
      this.audioQueue.push(processing);
    }
    if (!this.isPlaying) {
      this.isPlaying = true;
      this.scheduledTime = this.context.currentTime + this.initialBufferTime;
      this.scheduleNextBuffer();
    }
  }

  private createAudioBuffer(audioData: Float32Array): AudioBuffer {
    const buf = this.context.createBuffer(1, audioData.length, this.sampleRate);
    buf.getChannelData(0).set(audioData);
    return buf;
  }

  private scheduleNextBuffer() {
    const SCHEDULE_AHEAD = 0.2;

    while (
      this.audioQueue.length > 0 &&
      this.scheduledTime < this.context.currentTime + SCHEDULE_AHEAD
    ) {
      const audioData = this.audioQueue.shift()!;
      const audioBuffer = this.createAudioBuffer(audioData);
      const source = this.context.createBufferSource();
      this.activeSources.add(source);

      if (this.audioQueue.length === 0) {
        if (this.endOfQueueSource) this.endOfQueueSource.onended = null;
        this.endOfQueueSource = source;
        source.onended = () => {
          this.activeSources.delete(source);
          if (!this.audioQueue.length && this.endOfQueueSource === source) {
            this.endOfQueueSource = null;
            this.onComplete();
          }
        };
      } else {
        source.onended = () => {
          this.activeSources.delete(source);
        };
      }

      source.buffer = audioBuffer;
      source.connect(this.gainNode);
      const startTime = Math.max(this.scheduledTime, this.context.currentTime);
      source.start(startTime);
      this.scheduledTime = startTime + audioBuffer.duration;
    }

    if (this.audioQueue.length === 0) {
      if (this.isStreamComplete) {
        this.isPlaying = false;
        if (this.checkInterval) {
          clearInterval(this.checkInterval);
          this.checkInterval = null;
        }
      } else if (!this.checkInterval) {
        this.checkInterval = setInterval(() => {
          if (this.audioQueue.length > 0) this.scheduleNextBuffer();
        }, 100);
      }
    } else {
      const nextMs = (this.scheduledTime - this.context.currentTime) * 1000;
      setTimeout(() => this.scheduleNextBuffer(), Math.max(0, nextMs - 50));
    }
  }

  /** Corta reproducción inmediata — detiene todas las fuentes activas. */
  stop() {
    this.isPlaying = false;
    this.isStreamComplete = true;
    this.audioQueue = [];
    this.scheduledTime = this.context.currentTime;
    this.endOfQueueSource = null;

    for (const source of this.activeSources) {
      try {
        source.stop();
      } catch {
        /* ya terminó */
      }
      source.disconnect();
    }
    this.activeSources.clear();

    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }

  /** Gemini no enviará más audio en este turno — libera el mic tras drenar cola. */
  markInputComplete() {
    this.isStreamComplete = true;
    if (this.audioQueue.length === 0 && this.activeSources.size === 0) {
      this.isPlaying = false;
      if (this.checkInterval) {
        clearInterval(this.checkInterval);
        this.checkInterval = null;
      }
    } else {
      this.scheduleNextBuffer();
    }
  }

  setMuted(muted: boolean) {
    this.gainNode.gain.setValueAtTime(
      muted ? 0 : 1,
      this.context.currentTime,
    );
  }

  isActive(): boolean {
    return (
      this.isPlaying ||
      this.audioQueue.length > 0 ||
      this.activeSources.size > 0
    );
  }

  waitForDrain(maxMs = 4000): Promise<void> {
    return new Promise((resolve) => {
      const start = performance.now();
      const tick = () => {
        if (!this.isActive()) {
          resolve();
          return;
        }
        if (performance.now() - start > maxMs) {
          resolve();
          return;
        }
        setTimeout(tick, 40);
      };
      tick();
    });
  }
}
