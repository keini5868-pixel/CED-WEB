"use client";

import { Loader2, Mic, MicOff } from "lucide-react";
import { useRef, useState } from "react";

import { transcribeChatAudio } from "@/lib/api/chat";

type MicButtonProps = {
  onTranscription: (text: string) => void;
  disabled?: boolean;
};

export function MicButton({ onTranscription, disabled }: MicButtonProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const transcribeBlob = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    try {
      const text = await transcribeChatAudio(audioBlob);
      if (text) onTranscription(text);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Error transcribiendo. Intenta de nuevo.");
    } finally {
      setIsTranscribing(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        stopStream();
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        void transcribeBlob(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch {
      alert("Necesito permiso para usar el micrófono");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleClick = () => {
    if (disabled || isTranscribing) return;
    if (isRecording) {
      stopRecording();
    } else {
      void startRecording();
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || isTranscribing}
      className={`box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border transition active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px] ${
        isRecording
          ? "animate-pulse border-red-500 bg-red-500 text-white"
          : "border-cyan-800/50 bg-black/40 text-cyan-300 hover:bg-cyan-500/10"
      }`}
      aria-label={isRecording ? "Detener grabación" : "Grabar mensaje"}
      title={isRecording ? "Detener grabación" : "Dictar mensaje"}
    >
      {isTranscribing ? (
        <Loader2 className="h-[18px] w-[18px] shrink-0 animate-spin" />
      ) : isRecording ? (
        <MicOff className="h-[18px] w-[18px] shrink-0" />
      ) : (
        <Mic className="h-[18px] w-[18px] shrink-0" />
      )}
    </button>
  );
}
