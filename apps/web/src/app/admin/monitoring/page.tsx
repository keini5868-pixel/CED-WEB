"use client";

import { useEffect, useState } from "react";

import { HudPanel } from "@ced/ui";

import { cedApiPath } from "@/lib/api/ced-proxy";

type MonitoringData = {
  openai?: { ok?: boolean; model?: string };
  anthropic?: { ok?: boolean; model?: string };
  ready?: boolean;
};

export default function AdminMonitoringPage() {
  const [data, setData] = useState<MonitoringData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(cedApiPath("integrations"), {
          credentials: "same-origin",
        });
        if (!res.ok) {
          setError(`HTTP ${res.status}`);
          return;
        }
        setData(await res.json());
      } catch {
        setError("No se pudo cargar monitoreo");
      }
    })();
  }, []);

  return (
    <div className="space-y-6 p-4">
      <HudPanel title="MONITOREO OPENAI / COSTOS">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded border border-cyan-500/20 p-4">
            <p className="text-xs uppercase tracking-widest text-cyan-400/80">OpenAI Realtime</p>
            <p className="mt-2 text-sm">
              {data?.openai?.ok ? "✅ Conectado" : "❌ Revisar OPENAI_API_KEY"}
            </p>
            <p className="ced-hud-text-muted text-xs">Modelo: {data?.openai?.model ?? "—"}</p>
          </div>
          <div className="rounded border border-cyan-500/20 p-4">
            <p className="text-xs uppercase tracking-widest text-cyan-400/80">Claude (análisis)</p>
            <p className="mt-2 text-sm">
              {data?.anthropic?.ok ? "✅ OK" : "❌ Revisar ANTHROPIC_API_KEY"}
            </p>
            <p className="ced-hud-text-muted text-xs">Modelo: {data?.anthropic?.model ?? "—"}</p>
          </div>
        </div>
        {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
        <p className="ced-hud-text-muted mt-4 text-xs">
          Límites duros de voz aplicados en servidor. Tracking en{" "}
          <code>usage_logs</code> y <code>openai_usage_log</code> (post-migración 011).
        </p>
      </HudPanel>
    </div>
  );
}
