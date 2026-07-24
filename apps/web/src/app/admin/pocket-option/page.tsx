"use client";

import { useCallback, useEffect, useState } from "react";

import { HudPanel } from "@ced/ui";

import {
  fetchPocketOptionStatus,
  type PocketOptionStatus,
} from "@/lib/api/pocketOption";

function fmtTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function AdminPocketOptionPage() {
  const [data, setData] = useState<PocketOptionStatus | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const st = await fetchPocketOptionStatus();
      if (!st) {
        setDisabled(true);
        setData(null);
        setError(null);
        return;
      }
      setDisabled(false);
      setData(st);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-6 p-4">
      <HudPanel title="POCKET OPTION — DEMO (SOLO ADMIN)">
        <p className="mb-4 text-xs leading-relaxed text-cyan-500/80">
          Módulo experimental. Kill-switch{" "}
          <code className="text-cyan-300">POCKET_OPTION_MODULE_ENABLED</code>{" "}
          (default OFF). Solo cuenta demo. No expuesto a usuarios ni planes.
        </p>

        {disabled ? (
          <p className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            Módulo desactivado. En Railway:{" "}
            <code>POCKET_OPTION_MODULE_ENABLED=true</code> +{" "}
            <code>POCKET_OPTION_SSID</code> (sesión demo completa).
          </p>
        ) : null}

        {error ? <p className="text-sm text-red-400">{error}</p> : null}

        {data ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Stat
              label="Worker"
              value={data.running ? "RUNNING" : "STOPPED"}
              ok={data.running}
            />
            <Stat
              label="Conexión"
              value={data.connected ? "OK" : "OFF"}
              ok={data.connected}
            />
            <Stat
              label="Demo"
              value={
                data.is_demo === true
                  ? "SÍ"
                  : data.is_demo === false
                    ? "NO — BLOQUEADO"
                    : "—"
              }
              ok={data.is_demo === true}
            />
            <Stat
              label="Saldo demo"
              value={
                data.balance != null ? `$${data.balance.toFixed(2)}` : "—"
              }
              ok
            />
            <Stat label="Activo" value={data.asset || "—"} ok />
            <Stat
              label="Próximo slot"
              value={fmtTs(data.next_slot_at)}
              ok={!data.circuit_open}
            />
            <Stat
              label="Intervalo"
              value={`${data.interval_seconds}s`}
              ok
            />
            <Stat
              label="BOS"
              value={data.strategy_bos_enabled ? "ON" : "OFF"}
              ok={data.strategy_bos_enabled}
            />
            <Stat
              label="Alternadas"
              value={data.strategy_alt_enabled ? "ON" : "OFF"}
              ok={data.strategy_alt_enabled}
            />
          </div>
        ) : null}

        {data?.last_error ? (
          <p className="mt-4 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            Último error: {data.last_error}
          </p>
        ) : null}

        {data?.circuit_open ? (
          <p className="mt-2 text-xs text-amber-300">
            Circuit-breaker abierto — reconexión en curso.
          </p>
        ) : null}
      </HudPanel>

      <HudPanel title="OPERACIONES">
        {!data?.trades?.length ? (
          <p className="text-sm text-cyan-600">Sin operaciones aún.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-xs text-cyan-100/90">
              <thead className="text-[10px] uppercase tracking-wider text-cyan-500">
                <tr>
                  <th className="py-2 pr-3">Hora</th>
                  <th className="py-2 pr-3">Estrategia</th>
                  <th className="py-2 pr-3">Dir</th>
                  <th className="py-2 pr-3">Resultado</th>
                  <th className="py-2 pr-3">Nivel</th>
                  <th className="py-2">Motivo</th>
                </tr>
              </thead>
              <tbody>
                {[...data.trades].reverse().map((t) => (
                  <tr key={`${t.id}-${t.ts}`} className="border-t border-white/5">
                    <td className="py-2 pr-3 whitespace-nowrap">{fmtTs(t.ts)}</td>
                    <td className="py-2 pr-3 uppercase">{t.strategy}</td>
                    <td className="py-2 pr-3 uppercase">{t.direction}</td>
                    <td className="py-2 pr-3">{t.result}</td>
                    <td className="py-2 pr-3">{t.level?.toFixed?.(5) ?? t.level}</td>
                    <td className="py-2 text-cyan-400/80">{t.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </HudPanel>
    </div>
  );
}

function Stat({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="rounded border border-cyan-500/20 bg-black/40 px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-cyan-500/80">
        {label}
      </p>
      <p
        className={`mt-1 text-sm font-medium ${
          ok ? "text-cyan-100" : "text-amber-200"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
