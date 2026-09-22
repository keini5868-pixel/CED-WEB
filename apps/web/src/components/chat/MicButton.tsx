"use client";

import { Loader2, Mic, MicOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAudioAnalyser } from "@/hooks/useAudioAnalyser";
import { transcribeChatAudio } from "@/lib/api/chat";
import {
  markDictationAssistLock,
  sanitizeDictationTranscript,
} from "@/lib/chat/dictation-transcript";

type MicButtonProps = {
  getBaseText: () => string;
  onTextUpdate: (text: string) => void;
  onDictatingChange?: (active: boolean) => void;
  onLevel?: (level: number) => void;
  disabled?: boolean;
};

const MIN_RECORDING_MS = 400;
const MIN_AUDIO_BYTES = 800;
const MIN_PEAK_LEVEL = 0.04;

type SpeechRecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionResultEvent = {
  resultIndex: number;
  results: SpeechRecognitionResultList;
};

type SpeechRecognitionErrorEvent = {
  error: string;
};

type SpeechRecognitionResultList = {
  length: number;
  [index: number]: {
    isFinal: boolean;
    0: { transcript: string };
  };
};

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

function isLikelyIos(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/iPad|iPhone|iPod/i.test(ua)) return true;
  return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
}

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  if (isLikelyIos()) return null;
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function pickRecorderMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/aac",
    "audio/mpeg",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

function mergeBaseAndDictation(base: string, dictated: string): string {
  const b = base.trim();
  const d = dictated.trim();
  if (!d) return b;
  if (!b) return d;
  return `${b} ${d}`;
}

function buildTranscriptFromResults(results: SpeechRecognitionResultList): {
  final: string;
  interim: string;
} {
  let final = "";
  let interim = "";
  for (let i = 0; i < results.length; i++) {
    const piece = results[i]?.[0]?.transcript ?? "";
    if (results[i]?.isFinal) {
      final += piece;
    } else {
      interim += piece;
    }
  }
  return { final, interim };
}

export function MicButton({
  getBaseText,
  onTextUpdate,
  onDictatingChange,
  onLevel,
  disabled,
}: MicButtonProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [meterStream, setMeterStream] = useState<MediaStream | null>(null);

  const isRecordingRef = useRef(false);
  const baseTextRef = useRef("");
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recordingStartedAtRef = useRef<number | null>(null);
  const fallbackFromSpeechRef = useRef(false);
  const touchArmedRef = useRef(false);
  const peakLevelRef = useRef(0);

  const level = useAudioAnalyser(meterStream, isRecording);

  useEffect(() => {
    if (level > peakLevelRef.current) peakLevelRef.current = level;
    onLevel?.(isRecording ? level : 0);
  }, [level, isRecording, onLevel]);

  const setRecording = (active: boolean) => {
    isRecordingRef.current = active;
    setIsRecording(active);
    onDictatingChange?.(active);
    if (!active) onLevel?.(0);
  };

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setMeterStream(null);
  };

  const stopLiveRecognition = () => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    recognition.onend = null;
    recognition.onerror = null;
    recognition.onresult = null;
    try {
      recognition.stop();
    } catch {
      try {
        recognition.abort();
      } catch {
        /* ignore */
      }
    }
    recognitionRef.current = null;
  };

  const publishLiveTranscript = (results: SpeechRecognitionResultList) => {
    const { final, interim } = buildTranscriptFromResults(results);
    const dictated = sanitizeDictationTranscript(`${final}${interim}`);
    if (!dictated) {
      onTextUpdate(baseTextRef.current);
      return;
    }
    onTextUpdate(mergeBaseAndDictation(baseTextRef.current, dictated));
  };

  const startLiveDictation = () => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return false;

    baseTextRef.current = getBaseText().trim();
    const recognition = new Ctor();
    recognition.lang = "es-MX";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      publishLiveTranscript(event.results);
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        alert("Necesito permiso para usar el micrófono");
        setRecording(false);
        stopLiveRecognition();
        stopStream();
        return;
      }
      if (event.error === "no-speech" || event.error === "aborted") return;
      console.warn("[MicButton] speech error", event.error);
      if (
        isRecordingRef.current &&
        (event.error === "network" ||
          event.error === "service-not-allowed" ||
          event.error === "audio-capture")
      ) {
        fallbackFromSpeechRef.current = true;
        stopLiveRecognition();
        void startWhisperFallback(streamRef.current ?? undefined);
      }
    };

    recognition.onend = () => {
      if (fallbackFromSpeechRef.current) return;
      if (!isRecordingRef.current) return;
      try {
        recognition.start();
      } catch {
        setRecording(false);
        stopStream();
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setRecording(true);
      return true;
    } catch {
      recognitionRef.current = null;
      return false;
    }
  };

  const stopLiveDictation = () => {
    setRecording(false);
    stopLiveRecognition();
    stopStream();
  };

  const transcribeBlob = async (audioBlob: Blob) => {
    if (audioBlob.size < MIN_AUDIO_BYTES) return;
    if (peakLevelRef.current < MIN_PEAK_LEVEL) return;
    setIsTranscribing(true);
    try {
      const text = sanitizeDictationTranscript(await transcribeChatAudio(audioBlob));
      if (text) {
        onTextUpdate(mergeBaseAndDictation(baseTextRef.current, text));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (!/no se detectó voz|audio vacío/i.test(msg)) {
        alert(msg || "Error transcribiendo. Intenta de nuevo.");
      }
    } finally {
      setIsTranscribing(false);
      onDictatingChange?.(false);
    }
  };

  const startWhisperFallback = async (existingStream?: MediaStream) => {
    baseTextRef.current = getBaseText().trim();
    fallbackFromSpeechRef.current = false;
    try {
      const stream =
        existingStream ??
        streamRef.current ??
        (await navigator.mediaDevices.getUserMedia({
          audio: true,
        }));
      streamRef.current = stream;
      setMeterStream(stream);

      if (typeof MediaRecorder === "undefined") {
        stopStream();
        alert("Este navegador no permite grabar audio para dictar. Prueba Chrome o Safari actualizado.");
        setRecording(false);
        return;
      }

      const mimeType = pickRecorderMime();
      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      recordingStartedAtRef.current = Date.now();

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const startedAt = recordingStartedAtRef.current ?? Date.now();
        recordingStartedAtRef.current = null;
        const type = mediaRecorder.mimeType || mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type });
        stopStream();
        if (Date.now() - startedAt < MIN_RECORDING_MS) {
          onDictatingChange?.(false);
          return;
        }
        void transcribeBlob(audioBlob);
      };

      mediaRecorder.start(250);
      setRecording(true);
    } catch {
      alert("Necesito permiso para usar el micrófono");
      setRecording(false);
      stopStream();
    }
  };

  const stopWhisperFallback = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setRecording(false);
  };

  const startDictation = () => {
    void (async () => {
      peakLevelRef.current = 0;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        setMeterStream(stream);
        if (!startLiveDictation()) {
          await startWhisperFallback(stream);
        }
      } catch {
        alert("Necesito permiso para usar el micrófono");
        setRecording(false);
      }
    })();
  };

  const stopDictation = () => {
    if (recognitionRef.current) {
      stopLiveDictation();
      return;
    }
    stopWhisperFallback();
  };

  const handleToggle = () => {
    if (disabled || isTranscribing) return;
    markDictationAssistLock();
    if (isRecordingRef.current) {
      stopDictation();
    } else {
      startDictation();
    }
  };

  useEffect(() => {
    return () => {
      isRecordingRef.current = false;
      stopLiveRecognition();
      stopStream();
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const idle = !isRecording && !isTranscribing;

  return (
    <button
      type="button"
      onPointerDown={(e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          e.currentTarget.setPointerCapture(e.pointerId);
        } catch {
          /* ignore */
        }
        if (e.pointerType === "mouse") return;
        touchArmedRef.current = true;
        handleToggle();
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (touchArmedRef.current) {
          touchArmedRef.current = false;
          return;
        }
        handleToggle();
      }}
      disabled={disabled || isTranscribing}
      aria-pressed={isRecording}
      className={`box-border flex h-11 w-11 min-h-[44px] min-w-[44px] shrink-0 flex-none items-center justify-center rounded-full border transition active:scale-95 disabled:opacity-40 sm:h-10 sm:w-10 sm:min-h-[40px] sm:min-w-[40px] ${
        isRecording
          ? "animate-pulse border-red-500 bg-red-500 text-white shadow-[0_0_12px_rgba(239,68,68,0.45)]"
          : isTranscribing
            ? "border-cyan-700/40 bg-black/30 text-cyan-500"
            : "border-cyan-900/40 bg-black/25 text-cyan-700 hover:border-cyan-700/50 hover:bg-cyan-950/40 hover:text-cyan-400"
      }`}
      style={{ touchAction: "manipulation" }}
      aria-label={
        isRecording
          ? "Detener dictado"
          : isTranscribing
            ? "Transcribiendo…"
            : "Activar dictado por voz"
      }
      title={
        idle ? "Toca para dictar" : isRecording ? "Toca para detener" : "Transcribiendo…"
      }
    >
      {isTranscribing ? (
        <Loader2 className="h-[18px] w-[18px] shrink-0 animate-spin" />
      ) : isRecording ? (
        <Mic className="h-[18px] w-[18px] shrink-0" />
      ) : (
        <MicOff className="h-[18px] w-[18px] shrink-0 opacity-80" />
      )}
    </button>
  );
}
