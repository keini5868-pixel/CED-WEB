/** Alias de eventos OpenAI Realtime (Preview + GA). */

export function isResponseAudioDelta(type: string): boolean {
  return type === "response.audio.delta" || type === "response.output_audio.delta";
}

export function isResponseAudioDone(type: string): boolean {
  return type === "response.audio.done" || type === "response.output_audio.done";
}

export function isResponseAudioTranscriptDelta(type: string): boolean {
  return (
    type === "response.audio_transcript.delta" ||
    type === "response.output_audio_transcript.delta"
  );
}

export function isInputTranscriptionCompleted(type: string): boolean {
  return (
    type === "conversation.item.input_audio_transcription.completed" ||
    type === "input_audio_buffer.transcription.completed" ||
    type === "conversation.item.input_audio_transcription.done"
  );
}
