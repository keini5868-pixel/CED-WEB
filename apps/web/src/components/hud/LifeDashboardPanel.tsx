"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectGoogleCalendarFromLife,
  connectGoogleGmailFromLife,
  dispatchLifeChatPrompt,
} from "@/lib/lifeActions";
import {
  fetchHudCalendarEvents,
  fetchHudGmailMessages,
  type GmailCategory,
  type GmailHudMessage,
} from "@/lib/api/hud";
import { createHudCalendarEvent } from "@/lib/api/hudActions";
import { useHudLifeData, hasRealWeatherData } from "@/hooks/useHudLifeData";

const lifeBtnClass =
  "rounded border border-cyan-400/30 bg-transparent px-2 py-0.5 text-[10px] text-[#00ffff] transition hover:bg-cyan-400/10";

const GMAIL_TABS: { id: GmailCategory; label: string }[] = [
  { id: "primary", label: "📥 PRINCIPAL" },
  { id: "promotions", label: "🏷️ PROMO" },
  { id: "social", label: "👥 SOCIAL" },
  { id: "updates", label: "📋 ACTUALIZ." },
  { id: "forums", label: "🔔 FOROS" },
];

function LifeActionButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={lifeBtnClass}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}

function GmailHudPanel({
  connected,
  hint,
}: {
  connected: boolean;
  hint?: string;
}) {
  const [category, setCategory] = useState<GmailCategory>("primary");
  const [messages, setMessages] = useState<GmailHudMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (cat: GmailCategory) => {
    if (!connected) return;
    setLoading(true);
    setError(null);
    const data = await fetchHudGmailMessages(cat);
    setMessages(data.messages);
    if (data.error) setError(data.error);
    setLoading(false);
  }, [connected]);

  useEffect(() => {
    void load(category);
  }, [category, connected, load]);

  if (!connected) {
    return (
      <div className="rounded border border-cyan-900/50 bg-black/50 p-3">
        <p className="text-[10px] font-medium text-cyan-300">📧 GMAIL</p>
        <p className="ced-hud-text-muted mt-2 text-[10px]">
          {hint || "Conectar Gmail en CFG ⚙️"}
        </p>
        <LifeActionButton
          label="Conectar Gmail"
          onClick={() => void connectGoogleGmailFromLife()}
        />
      </div>
    );
  }

  return (
    <div className="rounded border border-cyan-900/50 bg-black/50 p-3">
      <p className="text-[10px] font-medium tracking-wider text-cyan-300">📧 GMAIL</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {GMAIL_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setCategory(tab.id)}
            className={[
              "rounded border px-1.5 py-0.5 text-[9px]",
              category === tab.id
                ? "border-cyan-400/60 bg-cyan-950/50 text-cyan-200"
                : "border-cyan-900/40 text-cyan-400/70 hover:bg-cyan-950/30",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <ul className="mt-2 max-h-36 space-y-1.5 overflow-y-auto text-[10px] text-cyan-100/90">
        {loading ? (
          <li className="ced-hud-text-muted">Cargando…</li>
        ) : messages.length ? (
          messages.map((msg) => (
            <li key={msg.id}>
              <button
                type="button"
                className="w-full text-left hover:text-cyan-200"
                onClick={() =>
                  dispatchLifeChatPrompt(
                    `léeme el email de ${msg.from} con asunto ${msg.subject}`,
                  )
                }
              >
                <span className="font-medium">{msg.from}</span>
                {" — "}
                {msg.subject}
                {msg.date ? (
                  <span className="ced-hud-text-muted block text-[9px]">{msg.date}</span>
                ) : null}
              </button>
            </li>
          ))
        ) : (
          <li className="ced-hud-text-muted">Sin correos en esta categoría.</li>
        )}
      </ul>
      {error ? (
        <p className="mt-1 text-[9px] text-amber-400">{error}</p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1">
        <LifeActionButton
          label="📖 Leer con CED"
          onClick={() => dispatchLifeChatPrompt("léeme mis emails importantes", "gmail")}
        />
      </div>
    </div>
  );
}

function CalendarHudPanel({
  connected,
  hint,
  todayEvents,
  weekEvents,
  onRefresh,
}: {
  connected: boolean;
  hint?: string;
  todayEvents: string[];
  weekEvents: string[];
  onRefresh: () => void;
}) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  const [saving, setSaving] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [needsReconnect, setNeedsReconnect] = useState(false);
  const [localToday, setLocalToday] = useState(todayEvents);
  const [localWeek, setLocalWeek] = useState(weekEvents);

  useEffect(() => {
    setLocalToday(todayEvents);
    setLocalWeek(weekEvents);
  }, [todayEvents, weekEvents]);

  useEffect(() => {
    if (!connected) return;
    void (async () => {
      const data = await fetchHudCalendarEvents();
      if (data.error) {
        setDetailError(data.error);
        setNeedsReconnect(Boolean(data.needs_reconnect));
      } else {
        setDetailError(null);
        setNeedsReconnect(false);
      }
      if (data.connected) {
        setLocalToday(data.today_events);
        setLocalWeek(data.week_events);
      }
    })();
  }, [connected]);

  const saveEvent = async () => {
    if (!title.trim() || !date.trim()) return;
    setSaving(true);
    setDetailError(null);
    const eventTitle = title.trim();
    const eventDate = date.trim();
    const eventTime = time.trim() || "09:00";
    try {
      const result = await createHudCalendarEvent({
        title: eventTitle,
        date: eventDate,
        time: eventTime,
      });
      if (!result.ok) {
        const msg = result.error || "No se pudo guardar.";
        setDetailError(msg);
        setNeedsReconnect(/permiso|reconecte|conectar calendar/i.test(msg));
        return;
      }
      setDetailError(null);
      setNeedsReconnect(false);
      setTitle("");
      const displayTime = eventTime.length === 5 ? eventTime : eventTime.slice(0, 5);
      const optimistic = `Hoy ${displayTime} — ${eventTitle}`;
      setLocalToday((prev) => {
        if (prev.some((line) => line.includes(eventTitle))) return prev;
        return prev[0]?.toLowerCase().includes("sin eventos") ? [optimistic] : [optimistic, ...prev];
      });
      onRefresh();
      void fetchHudCalendarEvents().then((data) => {
        if (data.error) {
          setDetailError(data.error);
          setNeedsReconnect(Boolean(data.needs_reconnect));
        } else {
          setDetailError(null);
          setNeedsReconnect(false);
        }
        if (data.today_events.length) setLocalToday(data.today_events);
        if (data.week_events.length) setLocalWeek(data.week_events);
      });
    } finally {
      setSaving(false);
    }
  };

  if (!connected) {
    return (
      <div className="rounded border border-cyan-900/50 bg-black/50 p-3">
        <p className="text-[10px] font-medium text-cyan-300">📅 CALENDARIO</p>
        <p className="ced-hud-text-muted mt-2 text-[10px]">
          {hint || "Conectar Calendar en CFG ⚙️"}
        </p>
        <LifeActionButton
          label="Conectar Calendar"
          onClick={() => void connectGoogleCalendarFromLife()}
        />
      </div>
    );
  }

  return (
    <div className="rounded border border-cyan-900/50 bg-black/50 p-3">
      <p className="text-[10px] font-medium tracking-wider text-cyan-300">📅 CALENDARIO</p>
      <p className="ced-hud-text-muted mt-2 text-[9px] uppercase tracking-wider">Hoy</p>
      <ul className="mt-1 space-y-0.5 text-[10px] text-cyan-100/90">
        {localToday.length ? (
          localToday.map((line, i) => <li key={`t-${i}`}>• {line}</li>)
        ) : (
          <li className="ced-hud-text-muted">• Sin eventos hoy</li>
        )}
      </ul>
      <p className="ced-hud-text-muted mt-2 text-[9px] uppercase tracking-wider">
        Próximos 7 días
      </p>
      <ul className="mt-1 max-h-24 space-y-0.5 overflow-y-auto text-[10px] text-cyan-100/90">
        {localWeek.length ? (
          localWeek.map((line, i) => <li key={`w-${i}`}>• {line}</li>)
        ) : (
          <li className="ced-hud-text-muted">• Sin eventos próximos</li>
        )}
      </ul>
      {detailError ? (
        <div className="mt-1 space-y-1">
          <p className="text-[9px] text-amber-400">{detailError}</p>
          {needsReconnect ? (
            <LifeActionButton
              label="↻ Reconectar Calendar"
              onClick={() => void connectGoogleCalendarFromLife()}
            />
          ) : null}
        </div>
      ) : null}
      <div className="mt-2 space-y-1">
        <p className="text-[9px] text-cyan-400/80">➕ Nuevo evento</p>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Nombre del evento…"
          className="w-full rounded border border-cyan-900/50 bg-black/60 px-2 py-1 text-[10px] text-cyan-100"
        />
        <div className="flex gap-1">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="flex-1 rounded border border-cyan-900/50 bg-black/60 px-2 py-1 text-[10px] text-cyan-100"
          />
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-24 rounded border border-cyan-900/50 bg-black/60 px-2 py-1 text-[10px] text-cyan-100"
          />
        </div>
        <LifeActionButton
          label={saving ? "GUARDANDO…" : "GUARDAR"}
          onClick={() => void saveEvent()}
          disabled={saving}
        />
      </div>
      <div className="mt-2">
        <LifeActionButton
          label="📅 Ver esta semana"
          onClick={() =>
            dispatchLifeChatPrompt("¿qué eventos tengo esta semana?", "calendar")
          }
        />
      </div>
    </div>
  );
}

function CompactLifeSection({
  icon,
  title,
  lines,
  actions,
}: {
  icon: string;
  title: string;
  lines: string[];
  actions?: React.ReactNode;
}) {
  return (
    <section className="rounded border border-cyan-900/40 bg-black/40 px-2.5 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[9px] font-medium uppercase tracking-wider text-cyan-400/90">
            {icon} {title}
          </p>
          <ul className="mt-1 space-y-0.5 text-[10px] text-cyan-100/85">
            {lines.slice(0, 2).map((line, i) => (
              <li key={`${title}-${i}`} className="truncate">
                {line}
              </li>
            ))}
          </ul>
        </div>
        {actions ? <div className="flex shrink-0 flex-col gap-0.5">{actions}</div> : null}
      </div>
    </section>
  );
}

export function LifeDashboardPanel() {
  const {
    data,
    refreshingConnections,
    loadingWeather,
    refresh,
    refreshConnections,
  } = useHudLifeData();

  const place = data.place || "Charlotte NC";
  const weatherReady = hasRealWeatherData(data.weather.lines);
  const weatherHeadline = weatherReady
    ? data.weather.lines[0] ?? "Charlotte NC"
    : loadingWeather
      ? "Cargando clima…"
      : "Charlotte NC";

  const todayEvents =
    data.calendar.today_events?.length
      ? data.calendar.today_events
      : data.calendar.events.slice(0, 3);
  const weekEvents =
    data.calendar.week_events?.length
      ? data.calendar.week_events
      : data.calendar.events.slice(3);

  return (
    <div className="space-y-2">
      <header className="flex items-center justify-between gap-2 rounded border border-cyan-500/20 bg-cyan-950/15 px-2.5 py-1.5">
        <p className="font-[family-name:var(--font-orbitron)] text-[9px] tracking-wider text-cyan-300">
          📅 {data.date_label}
        </p>
        <div className="flex items-center gap-2">
          {refreshingConnections ? (
            <span className="ced-hud-text-muted animate-pulse text-[8px]">
              Gmail/Calendar…
            </span>
          ) : loadingWeather ? (
            <span className="ced-hud-text-muted text-[8px] opacity-50">Clima en fondo</span>
          ) : (
            <span className="ced-hud-text-muted text-[8px] opacity-60">Auto</span>
          )}
          <LifeActionButton label="↻" onClick={() => void refresh()} />
        </div>
      </header>

      <div className="grid gap-2 lg:grid-cols-2">
        <GmailHudPanel connected={data.gmail.connected} hint={data.gmail.hint} />
        <CalendarHudPanel
          connected={data.calendar.connected}
          hint={data.calendar.hint}
          todayEvents={todayEvents}
          weekEvents={weekEvents}
          onRefresh={() => void refreshConnections()}
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-3">
        <CompactLifeSection
          icon="🌤️"
          title="CLIMA"
          lines={[weatherHeadline, ...(data.weather.lines.slice(1, 2) || [])]}
          actions={
            <LifeActionButton
              label="Pregunta"
              onClick={() =>
                dispatchLifeChatPrompt(`¿qué clima hay hoy en ${place}?`, "weather")
              }
            />
          }
        />
        <CompactLifeSection
          icon="🌬️"
          title="AIRE"
          lines={data.air_quality.lines}
          actions={
            <LifeActionButton
              label="Pregunta"
              onClick={() =>
                dispatchLifeChatPrompt(
                  `¿cómo está la calidad del aire en ${place} hoy?`,
                  "weather",
                )
              }
            />
          }
        />
        <CompactLifeSection
          icon="🌿"
          title="POLEN"
          lines={data.pollen.lines}
          actions={
            <LifeActionButton
              label="Pregunta"
              onClick={() =>
                dispatchLifeChatPrompt(
                  `¿cuáles son los niveles de polen en ${place} hoy?`,
                  "weather",
                )
              }
            />
          }
        />
      </div>
    </div>
  );
}
