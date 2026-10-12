"use client";

import { useCallback, useEffect, useState } from "react";

import { HudPanel } from "@ced/ui";

import {
  fetchAdminSentinel,
  setAdminSentinelEnabled,
  type SentinelCheck,
  type SentinelEvent,
  type SentinelStatus,
} from "@/lib/api/admin";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function levelMark(level: SentinelCheck["level"] | SentinelEvent["level"]): string {
  if (level === "ok") return "OK";
  if (level === "error") return "FALLO";
  return "REVISAR";
}

function levelClass(level: string): string {
  if (level === "ok") return "text-emerald-300";
  if (level === "error") return "text-red-400";
  return "text-amber-300";
}

function CheckList({ items, empty }: { items: SentinelCheck[]; empty: string }) {
  if (items.length === 0) {
    return <p className="ced-hud-text-muted text-sm">{empty}</p>;
  }
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.area} className="rounded border border-cyan-500/20 p-3">
          <p className={`text-[10px] font-semibold uppercase tracking-[0.16em] ${levelClass(item.level)}`}>
            {levelMark(item.level)}
            {typeof item.latency_ms === "number" ? ` · ${item.latency_ms} ms` : ""}
          </p>
          <p className="mt-1 text-sm">{item.title}</p>
          {item.detail ? <p className="ced-hud-text-muted mt-1 text-xs">{item.detail}</p> : null}
        </li>
      ))}
    </ul>
  );
}

export default function AdminSentinelPage() {
  const [data, setData] = useState<SentinelStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await fetchAdminSentinel();
      setData(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo leer el centinela");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 8000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function toggle() {
    if (!data || busy) return;
    setBusy(true);
    try {
      const next = await setAdminSentinelEnabled(!data.enabled);
      setData(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cambiar la guardia");
    } finally {
      setBusy(false);
    }
  }

  const checks = data?.checks ?? [];
  const review = checks.filter((item) => item.level !== "ok");
  const healthy = checks.filter((item) => item.level === "ok");
  const events = data?.events ?? [];

  return (
    <div className="space-y-6 p-4">
      <HudPanel title="CENTINELA">
        <p className="ced-hud-text-body max-w-3xl">
          Guardia solo tuya. Si la dejas activa, sigue en el servidor aunque cierres
          el teléfono. Al volver, el parte y la bitácora están en esta pestaña.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void toggle()}
            disabled={busy || !data}
            className={`rounded border px-4 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold uppercase tracking-[0.16em] transition disabled:opacity-50 ${
              data?.enabled
                ? "border-red-400/70 bg-red-500/10 text-red-200 hover:bg-red-500/20"
                : "border-emerald-400/70 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
            }`}
          >
            {busy ? "Procesando…" : data?.enabled ? "Apagar guardia" : "Activar guardia"}
          </button>
          <p className={`text-sm ${data?.enabled ? "text-emerald-300" : "ced-hud-text-muted"}`}>
            {data?.enabled
              ? `Activo desde ${formatWhen(data.enabled_at)}${data.running ? " · vigilando" : ""}`
              : "Apagado"}
          </p>
        </div>
        {data?.checked_at ? (
          <p className="ced-hud-text-muted mt-3 text-xs">
            Última pasada {formatWhen(data.checked_at)}
          </p>
        ) : null}
        {data && !data.persistent ? (
          <p className="mt-3 text-xs text-amber-300">
            Esta bitácora vive en el proceso actual. Para que sobreviva un reinicio
            del servidor, aplica la migración 045 en Supabase.
          </p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
        <p className="ced-hud-text-muted mt-4 text-xs">
          Con la guardia activa, si una imagen o un documento no coincide con lo
          pedido, se rehace y quien espera ve: Corrigiendo datos para darlo con más
          precisión…
        </p>
      </HudPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <HudPanel title="A REVISAR">
          <CheckList
            items={review}
            empty={
              data?.enabled
                ? "Sin fallos en la última pasada."
                : "Activa la guardia para empezar el parte."
            }
          />
        </HudPanel>
        <HudPanel title="EN ORDEN">
          <CheckList
            items={healthy}
            empty={data?.enabled ? "La primera pasada está en curso." : "Aún no hay lecturas."}
          />
        </HudPanel>
      </div>

      <HudPanel title="BITÁCORA">
        {events.length === 0 ? (
          <p className="ced-hud-text-muted text-sm">
            Aquí quedan los cambios, los errores y las correcciones de mientras no estabas.
          </p>
        ) : (
          <ul className="max-h-[28rem] space-y-2 overflow-y-auto">
            {events.map((event) => (
              <li key={event.id} className="rounded border border-cyan-500/15 px-3 py-2">
                <p className="ced-hud-text-muted text-[10px] uppercase tracking-[0.14em]">
                  {formatWhen(event.at)} · {event.area} ·{" "}
                  <span className={levelClass(event.level)}>{levelMark(event.level)}</span>
                </p>
                <p className="mt-1 text-sm">{event.title}</p>
                {event.detail ? (
                  <p className="ced-hud-text-muted mt-1 text-xs">{event.detail}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </HudPanel>
    </div>
  );
}
