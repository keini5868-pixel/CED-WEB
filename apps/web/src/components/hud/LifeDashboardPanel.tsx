"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectGoogleCalendarFromLife,
  connectGoogleGmailFromLife,
  dispatchLifeVoicePrompt,
} from "@/lib/lifeActions";
import {
  createLifeFallback,
  fetchHudLife,
  type LifeDashboardSnapshot,
} from "@/lib/api/hud";

const REFRESH_MS = 30 * 60 * 1000;

const lifeBtnClass =
  "rounded border border-cyan-400/30 bg-transparent px-2.5 py-1 text-[11px] text-[#00ffff] transition hover:bg-cyan-400/10";

function LifeActionButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className={lifeBtnClass} onClick={onClick}>
      {label}
    </button>
  );
}

function LifeSection({
  icon,
  title,
  lines,
  hint,
  actions,
}: {
  icon: string;
  title: string;
  lines: string[];
  hint?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className="rounded border border-cyan-900/50 bg-black/50 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-[0.18em] text-cyan-400">
          {icon} {title}
        </h3>
      </div>
      <ul className="mt-2 space-y-1 text-xs leading-relaxed text-zinc-200">
        {lines.map((line, idx) => (
          <li key={`${title}-${idx}-${line.slice(0, 24)}`} className="flex gap-2">
            <span className="text-cyan-600">•</span>
            <span>{line}</span>
          </li>
        ))}
      </ul>
      {hint ? (
        <p className="ced-hud-text-muted mt-2 text-[10px] italic">{hint}</p>
      ) : null}
      {actions ? (
        <div className="mt-2 flex flex-wrap gap-2">{actions}</div>
      ) : null}
    </section>
  );
}

export function LifeDashboardPanel() {
  const [data, setData] = useState<LifeDashboardSnapshot>(() => createLifeFallback());
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const snapshot = await fetchHudLife();
      setData(snapshot);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const place = data.place || "Charlotte NC";
  const weatherHeadline = data.weather.lines[0] ?? "Buscando clima…";
  const weatherExtra = data.weather.lines.slice(1);

  const calendarLines =
    data.calendar.connected && data.calendar.events.length
      ? data.calendar.events
      : data.calendar.connected
        ? ["Sin eventos para hoy."]
        : [data.calendar.hint || "Conectar Calendar en CFG ⚙️"];

  const gmailLines = data.gmail.connected
    ? [
        `${data.gmail.unread_count} email${data.gmail.unread_count === 1 ? "" : "s"} sin leer`,
        ...data.gmail.messages,
      ]
    : [data.gmail.hint || "Conectar Gmail en CFG ⚙️"];

  return (
    <div className="space-y-3">
      <header className="rounded border border-cyan-500/30 bg-cyan-950/20 px-3 py-2 text-center">
        <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.2em] text-cyan-300">
          📅 HOY — {data.date_label}
        </p>
        {data.place ? (
          <p className="ced-hud-text-muted mt-1 text-[10px]">{data.place}</p>
        ) : null}
        {refreshing ? (
          <p className="ced-hud-text-muted mt-1 text-[9px]">Actualizando…</p>
        ) : null}
      </header>

      <LifeSection
        icon="🌤️"
        title="CLIMA"
        lines={[weatherHeadline, ...weatherExtra]}
        actions={
          <>
            <LifeActionButton
              label="Preguntar a CED"
              onClick={() =>
                dispatchLifeVoicePrompt(`¿qué clima hay hoy en ${place}?`)
              }
            />
            <LifeActionButton label="Actualizar" onClick={() => void refresh()} />
          </>
        }
      />

      <LifeSection
        icon="📅"
        title="CALENDARIO"
        lines={calendarLines}
        actions={
          data.calendar.connected ? (
            <>
              <LifeActionButton
                label="Agregar evento"
                onClick={() =>
                  dispatchLifeVoicePrompt("Quiero agendar un evento en mi calendario")
                }
              />
              <LifeActionButton
                label="Ver todos"
                onClick={() =>
                  dispatchLifeVoicePrompt("¿qué eventos tengo esta semana?")
                }
              />
            </>
          ) : (
            <LifeActionButton
              label="Conectar Calendar"
              onClick={() => void connectGoogleCalendarFromLife()}
            />
          )
        }
      />

      <LifeSection
        icon="📧"
        title="GMAIL"
        lines={gmailLines}
        actions={
          data.gmail.connected ? (
            <>
              <LifeActionButton
                label="Leer emails"
                onClick={() =>
                  dispatchLifeVoicePrompt("¿tengo emails importantes?")
                }
              />
              <LifeActionButton
                label="Enviar email"
                onClick={() =>
                  dispatchLifeVoicePrompt("Quiero enviar un email")
                }
              />
            </>
          ) : (
            <LifeActionButton
              label="Conectar Gmail"
              onClick={() => void connectGoogleGmailFromLife()}
            />
          )
        }
      />

      <LifeSection
        icon="🌬️"
        title="CALIDAD DEL AIRE"
        lines={data.air_quality.lines}
        actions={
          <LifeActionButton
            label="Preguntar a CED"
            onClick={() =>
              dispatchLifeVoicePrompt(`¿cómo está la calidad del aire en ${place} hoy?`)
            }
          />
        }
      />

      <LifeSection
        icon="🌿"
        title="POLEN"
        lines={data.pollen.lines}
        actions={
          <LifeActionButton
            label="Preguntar a CED"
            onClick={() =>
              dispatchLifeVoicePrompt(`¿cuáles son los niveles de polen en ${place} hoy?`)
            }
          />
        }
      />

      <p className="ced-hud-text-muted text-center text-[9px]">
        Actualizado {new Date(data.updated_at).toLocaleTimeString("es-MX")}
        {" · "}
        refresh 30 min
      </p>
    </div>
  );
}
