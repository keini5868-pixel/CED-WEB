"use client";

import { useEffect, useState } from "react";

import {
  voiceTelemetry,
  type VoiceTelemetrySnapshot,
} from "@/lib/voice/voiceTelemetry";

export function useVoiceTelemetry(): VoiceTelemetrySnapshot {
  const [snap, setSnap] = useState<VoiceTelemetrySnapshot>(() =>
    voiceTelemetry.getSnapshot(),
  );

  useEffect(() => {
    return voiceTelemetry.subscribe(() => {
      setSnap(voiceTelemetry.getSnapshot());
    });
  }, []);

  return snap;
}
