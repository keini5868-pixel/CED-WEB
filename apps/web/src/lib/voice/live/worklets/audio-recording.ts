/** Worklet de captura — ~40 ms por chunk (OpenAI Realtime cookbook). */

const AudioRecordingWorklet = `
class AudioProcessingWorklet extends AudioWorkletProcessor {
  bufferSize = Math.max(480, Math.floor(sampleRate * 0.04));
  buffer = new Int16Array(this.bufferSize);
  bufferWriteIndex = 0;

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      const s = Math.max(-1, Math.min(1, channel[i]));
      this.buffer[this.bufferWriteIndex++] = s < 0 ? s * 32768 : s * 32767;
      if (this.bufferWriteIndex >= this.bufferSize) {
        this.port.postMessage({
          event: "chunk",
          data: { int16arrayBuffer: this.buffer.slice(0, this.bufferSize).buffer },
        });
        this.bufferWriteIndex = 0;
      }
    }
    return true;
  }
}
`;

export default AudioRecordingWorklet;
