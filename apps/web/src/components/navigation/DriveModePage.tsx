"use client";

import Link from "next/link";
import { useEffect } from "react";
import { MapPin, Navigation } from "lucide-react";

import { CedVoiceControls } from "@/components/voice/CedVoiceControls";
import {
  CedHistoryPanel,
  CedSettingsModal,
  CedStopConfirmModal,
} from "@/components/voice/CedVoiceModals";
import { DriveMapView } from "@/components/navigation/DriveMapView";
import { useGeolocation } from "@/hooks/useGeolocation";
import { useCedVoiceSession } from "@/hooks/useCedVoiceSession";
import { useUsageBalance } from "@/hooks/useUsageBalance";
import { prefetchEphemeralToken } from "@/lib/voice/ephemeralTokenCache";

export function DriveModePage() {
  const { refresh: refreshUsage } = useUsageBalance();
  const { position, error: geoError, loading: geoLoading } = useGeolocation(true);
  const voice = useCedVoiceSession(refreshUsage);

  useEffect(() => {
    prefetchEphemeralToken();
  }, []);

  const gpsLabel = geoLoading
    ? "Buscando GPS…"
    : geoError
      ? "GPS off"
      : position
        ? `±${Math.round(position.accuracy)} m`
        : "GPS…";

  return (
    <div className="fixed inset-0 flex flex-col bg-black">
      <DriveMapView position={position} className="absolute inset-0" />

      <div className="pointer-events-none relative z-10 flex h-full flex-col">
        <header className="pointer-events-auto flex items-center justify-between gap-2 bg-gradient-to-b from-black/80 to-transparent px-3 py-3 sm:px-4">
          <Link
            href="/dashboard"
            className="rounded border border-cyan-500/40 bg-black/70 px-3 py-1.5 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-300 sm:text-xs"
          >
            ← DASHBOARD
          </Link>
          <div className="flex items-center gap-2 rounded border border-cyan-500/30 bg-black/70 px-2 py-1.5">
            <MapPin className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-[10px] text-cyan-200 sm:text-xs">{gpsLabel}</span>
          </div>
        </header>

        <div className="flex-1" />

        <div className="pointer-events-auto border-t border-cyan-500/25 bg-black/75 px-3 py-3 backdrop-blur-md sm:px-4">
          <div className="mb-2 flex items-center gap-2">
            <Navigation className="h-4 w-4 text-cyan-400" />
            <p className="font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-widest text-cyan-300">
              MODO CONDUCIR
            </p>
          </div>

          <p className="mb-3 text-center font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wide text-[#00e5ff]">
            {voice.statusLabel}
          </p>

          {geoError ? (
            <p className="mb-2 text-center text-xs text-amber-300">{geoError}</p>
          ) : null}

          {voice.errorMessage ? (
            <p className="mb-2 text-center text-xs text-red-300">{voice.errorMessage}</p>
          ) : null}

          <CedVoiceControls
            micOn={voice.micOn}
            micBusy={voice.micBusy}
            cameraOn={voice.cameraOn}
            muted={voice.muted}
            paused={voice.paused}
            onMic={() => void voice.toggleMic()}
            onCamera={() => void voice.toggleCamera()}
            onMute={() => voice.setMuted((m) => !m)}
            onPause={voice.togglePause}
            onStop={() => voice.setStopConfirmOpen(true)}
            onHistory={() => voice.setHistoryOpen(true)}
            onChat={() => undefined}
            onSettings={() => voice.setSettingsOpen(true)}
            onFiles={() => undefined}
          />

          <p className="mt-2 text-center text-[10px] text-cyan-700">
            Rutas por voz — próxima fase
          </p>
        </div>
      </div>

      <CedStopConfirmModal
        open={voice.stopConfirmOpen}
        onClose={() => voice.setStopConfirmOpen(false)}
        onConfirm={() => {
          voice.stopSession();
          voice.setStopConfirmOpen(false);
        }}
      />
      <CedSettingsModal
        open={voice.settingsOpen}
        onClose={() => voice.setSettingsOpen(false)}
        prefs={voice.prefs}
        onSave={voice.updatePrefs}
        micOn={voice.micOn}
        onApplyVoice={voice.applyVoiceChange}
      />
      <CedHistoryPanel
        open={voice.historyOpen}
        onClose={() => voice.setHistoryOpen(false)}
      />
    </div>
  );
}
