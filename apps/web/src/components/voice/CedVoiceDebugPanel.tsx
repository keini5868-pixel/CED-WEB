"use client";

import { useEffect, useState } from "react";

import { useVoiceTelemetry } from "@/hooks/useVoiceTelemetry";
import { isVoiceDebugEnabled } from "@/lib/voice/voiceTelemetry";

function latencyColor(ms: number | null): string {
  if (ms === null) return "text-zinc-400";
  if (ms < 800) return "text-emerald-400";
  if (ms < 1500) return "text-amber-400";
  return "text-red-400";
}

function wsLabel(state: string): string {
  switch (state) {
    case "connected":
      return "Conectado";
    case "connecting":
      return "Conectando…";
    case "closed":
      return "Cerrado";
    case "error":
      return "Error";
    default:
      return "Desconectado";
  }
}

/** Panel dev: latencia E2E / red / playback, audio, WS, log de turnos. */
export function CedVoiceDebugPanel() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const t = useVoiceTelemetry();

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || !isVoiceDebugEnabled()) return null;

  const e2e = t.e2eLatencyMs ?? t.lastLatencyMs;

  return (
    <div className="pointer-events-none fixed bottom-3 right-3 z-50 flex flex-col items-end gap-2">
      <div
        className="pointer-events-auto rounded-md border border-cyan-900/60 bg-black/90 px-3 py-2 font-mono text-[11px] shadow-lg backdrop-blur-sm"
        role="status"
        aria-live="polite"
      >
        <p className={latencyColor(e2e)}>
          E2E: {e2e !== null ? `${e2e} ms` : "—"}
          {e2e !== null && e2e < 1500 ? " ✓" : e2e !== null ? " ⚠" : ""}
        </p>
        <p className="text-zinc-400">
          Cola: {t.pipelineQueueMs !== null ? `${t.pipelineQueueMs} ms` : "—"} ·
          Gap:{" "}
          {t.pipelinePacketGapMs !== null ? `${t.pipelinePacketGapMs} ms` : "—"} ·
          Underruns:{" "}
          <span className={t.pipelineUnderruns > 0 ? "text-amber-400" : ""}>
            {t.pipelineUnderruns}
          </span>
        </p>
        <p className="text-zinc-400">
          Red: {t.networkLatencyMs !== null ? `${t.networkLatencyMs} ms` : "—"} ·
          Play:{" "}
          {t.playbackLatencyMs !== null ? `${t.playbackLatencyMs} ms` : "—"}
        </p>
        <p className="text-cyan-300/90">
          Audio: {t.inputSampleRate / 1000}kHz/PCM ✓ · {t.chunkMs}ms ·{" "}
          {t.captureEngine}
        </p>
        <p className="text-zinc-400">
          ↑{t.chunksSentPerSec}/s ↓{t.chunksRecvPerSec}/s · Voz: {t.activeVoice}{" "}
          · WS: {wsLabel(t.wsState)}
        </p>
      </div>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="pointer-events-auto rounded border border-cyan-800/50 bg-black/85 px-2 py-1 font-mono text-[10px] text-cyan-400 hover:bg-cyan-950/50"
      >
        {open ? "Ocultar log voz" : "Log voz"}
      </button>

      {open ? (
        <div className="pointer-events-auto max-h-64 w-[min(92vw,380px)] overflow-y-auto rounded-md border border-cyan-900/50 bg-black/92 p-2 font-mono text-[10px] text-zinc-300 shadow-xl">
          <p className="mb-2 text-cyan-500">
            ↑{t.messagesSent} env · ↓{t.messagesReceived} recv · avg{" "}
            {t.avgLatencyMs ?? "—"} ms
          </p>
          {t.lastError ? (
            <p className="mb-2 text-red-400">ERR: {t.lastError}</p>
          ) : null}
          {t.turnLogs.length === 0 ? (
            <p className="text-zinc-500">Sin turnos aún…</p>
          ) : (
            <ul className="space-y-1">
              {t.turnLogs.map((log) => (
                <li key={log.id} className="border-b border-zinc-800/80 pb-1">
                  <span className="text-zinc-500">
                    {new Date(log.at).toLocaleTimeString()}
                  </span>{" "}
                  <span className="text-cyan-600">{log.kind}</span>
                  {log.latencyMs !== undefined ? (
                    <span className={latencyColor(log.latencyMs)}>
                      {" "}
                      +{log.latencyMs}ms
                    </span>
                  ) : null}
                  {log.detail ? (
                    <span className="block truncate text-zinc-400">
                      {log.detail}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
