"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { CedPresenterMascot } from "@/components/voice/CedPresenterMascot";
import { useCedOwnerUi } from "@/contexts/CedOwnerUiContext";

const STORAGE_KEY = "ced-presenter-on";

type PresenterSession = {
  on: boolean;
  exiting: boolean;
  toggle: () => void;
  beginExitForAssist: (then?: () => void) => void;
  setAssistLive: (live: boolean) => void;
};

const PresenterSessionContext = createContext<PresenterSession | null>(null);

function readStoredOn(): boolean {
  try {
    return sessionStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeStoredOn(on: boolean) {
  try {
    sessionStorage.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    /* private mode */
  }
}

export function CedPresenterSessionProvider({ children }: { children: ReactNode }) {
  const owner = useCedOwnerUi();
  const [on, setOn] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [assistLive, setAssistLive] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const exitTimer = useRef(0);

  const stopAudio = useCallback(() => {
    setStream((current) => {
      current?.getTracks().forEach((t) => t.stop());
      return null;
    });
  }, []);

  const startAudio = useCallback(async () => {
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      });
      setStream(next);
    } catch {
      setStream(null);
    }
  }, []);

  useEffect(() => {
    if (!owner) {
      setOn(false);
      setExiting(false);
      stopAudio();
      writeStoredOn(false);
      return;
    }
    if (readStoredOn()) {
      setOn(true);
      void startAudio();
    }
  }, [owner, startAudio, stopAudio]);

  useEffect(() => () => window.clearTimeout(exitTimer.current), []);

  const toggle = useCallback(() => {
    if (!owner) return;
    if (on) {
      window.clearTimeout(exitTimer.current);
      setExiting(true);
      exitTimer.current = window.setTimeout(() => {
        stopAudio();
        setOn(false);
        setExiting(false);
        writeStoredOn(false);
      }, 720);
      return;
    }
    setExiting(false);
    setOn(true);
    writeStoredOn(true);
    void startAudio();
  }, [owner, on, startAudio, stopAudio]);

  const beginExitForAssist = useCallback(
    (then?: () => void) => {
      if (!on) {
        then?.();
        return;
      }
      window.clearTimeout(exitTimer.current);
      setExiting(true);
      exitTimer.current = window.setTimeout(() => {
        stopAudio();
        setOn(false);
        setExiting(false);
        writeStoredOn(false);
        then?.();
      }, 720);
    },
    [on, stopAudio],
  );

  const value = useMemo(
    () => ({
      on,
      exiting,
      toggle,
      beginExitForAssist,
      setAssistLive,
    }),
    [on, exiting, toggle, beginExitForAssist],
  );

  return (
    <PresenterSessionContext.Provider value={value}>
      {children}
      {owner ? (
        <CedPresenterMascot
          visible={(on || exiting) && (!assistLive || exiting)}
          exiting={exiting}
          audioStream={stream}
        />
      ) : null}
    </PresenterSessionContext.Provider>
  );
}

export function useCedPresenterSession(): PresenterSession {
  const ctx = useContext(PresenterSessionContext);
  if (!ctx) {
    return {
      on: false,
      exiting: false,
      toggle: () => undefined,
      beginExitForAssist: (then) => then?.(),
      setAssistLive: () => undefined,
    };
  }
  return ctx;
}
