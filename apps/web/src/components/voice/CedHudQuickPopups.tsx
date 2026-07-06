"use client";

import { useCallback, useEffect, useState } from "react";

import { createHudCalendarEvent, sendHudGmail } from "@/lib/api/hudActions";
import {
  connectGoogleCalendarFromLife,
  connectGoogleGmailFromLife,
  dispatchLifeVoicePrompt,
} from "@/lib/lifeActions";
import {
  saveReminderWithSync,
  upcomingReminders,
  type CedReminder,
} from "@/lib/hud/remindersStorage";
import { useHudLifeData } from "@/hooks/useHudLifeData";

export type HudQuickPopupId = "weather" | "calendar" | "events" | "gmail" | null;

const popupShell =
  "fixed bottom-20 left-1/2 z-[1000] min-w-[260px] max-w-[320px] -translate-x-1/2 rounded-lg border border-cyan-400/40 bg-black/95 p-4 text-xs text-[#00ffff] shadow-[0_0_24px_rgba(0,255,255,0.15)]";

const hudInput =
  "mt-1 w-full rounded border border-cyan-400/30 bg-cyan-400/5 px-2.5 py-1.5 text-xs text-[#00ffff] outline-none focus:border-cyan-400/60";

const hudBtn =
  "mt-1 w-full cursor-pointer rounded border border-[#00ffff] bg-transparent px-3 py-1.5 text-[11px] text-[#00ffff] transition hover:bg-cyan-400/10";

function HudPopupButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className={hudBtn} onClick={onClick}>
      {label}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="mt-2 block text-[10px] uppercase tracking-wider text-cyan-400/80">
      {label}
      {children}
    </label>
  );
}

export function CedHudQuickPopups({
  active,
  onClose,
}: {
  active: HudQuickPopupId;
  onClose: () => void;
}) {
  const { data, refresh, weatherSummary } = useHudLifeData();
  const [reminders, setReminders] = useState<CedReminder[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [calTitle, setCalTitle] = useState("");
  const [calDate, setCalDate] = useState("");
  const [calTime, setCalTime] = useState("09:00");
  const [calReminder, setCalReminder] = useState("15");
  const [remText, setRemText] = useState("");
  const [remDate, setRemDate] = useState("");
  const [remTime, setRemTime] = useState("09:00");
  const [mailTo, setMailTo] = useState("");
  const [mailSubject, setMailSubject] = useState("");
  const [mailBody, setMailBody] = useState("");

  const reloadReminders = useCallback(() => setReminders(upcomingReminders()), []);

  useEffect(() => {
    if (!active) return;
    reloadReminders();
    setStatus(null);
  }, [active, reloadReminders]);

  if (!active) return null;

  const { temp, condition } = weatherSummary();

  const saveCalendar = async () => {
    if (!calTitle.trim() || !calDate) {
      setStatus("Complete nombre y fecha.");
      return;
    }
    const result = await createHudCalendarEvent({
      title: calTitle.trim(),
      date: calDate,
      time: calTime || "09:00",
      reminder_minutes: Number(calReminder) || undefined,
    });
    setStatus(result.ok ? "Evento guardado." : result.error || "Error al guardar.");
    if (result.ok) {
      setCalTitle("");
      void refresh();
    }
  };

  const saveReminderItem = async () => {
    if (!remText.trim() || !remDate) {
      setStatus("Complete recordatorio y fecha.");
      return;
    }
    const result = await saveReminderWithSync({
      text: remText.trim(),
      date: remDate,
      time: remTime || "09:00",
    });
    setRemText("");
    reloadReminders();
    if (result.synced) {
      setStatus("Recordatorio creado.");
    } else {
      setStatus(result.error || "Guardado localmente; CED puede no verlo aún.");
    }
  };

  const sendMail = async () => {
    if (!mailTo.trim() || !mailSubject.trim() || !mailBody.trim()) {
      setStatus("Complete Para, Asunto y Mensaje.");
      return;
    }
    const result = await sendHudGmail({
      to: mailTo.trim(),
      subject: mailSubject.trim(),
      body: mailBody.trim(),
    });
    setStatus(result.ok ? "Email enviado." : result.error || "Error al enviar.");
    if (result.ok) {
      setMailTo("");
      setMailSubject("");
      setMailBody("");
      void refresh();
    }
  };

  return (
    <>
      <button type="button" className="fixed inset-0 z-[999]" aria-label="Cerrar popup" onClick={onClose} />
      <div className={popupShell} onClick={(e) => e.stopPropagation()}>
        {active === "weather" ? (
          <>
            <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-wider">🌤️ CLIMA</p>
            <p className="mt-2">{data.place || "Charlotte, NC"}</p>
            <p className="mt-1">{temp} · {condition}</p>
            <p className="mt-1 text-[#00ffff]/80">{data.weather.lines.slice(1).join(" · ") || "—"}</p>
            <p className="mt-2 text-[#00ffff]/70">Calidad aire: {data.air_quality.lines[0] ?? "—"}</p>
            <p className="text-[#00ffff]/70">Polen: {data.pollen.lines[0] ?? "—"}</p>
            <div className="mt-3 border-t border-cyan-900/50 pt-2">
              <HudPopupButton label="Preguntar a CED" onClick={() => { dispatchLifeVoicePrompt("¿qué clima hay hoy?"); onClose(); }} />
              <HudPopupButton label="Actualizar" onClick={() => void refresh()} />
            </div>
          </>
        ) : null}

        {active === "calendar" ? (
          <>
            <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-wider">📅 CALENDARIO</p>
            <p className="mt-2 text-[#00ffff]/80">Hoy: {data.calendar.connected ? data.calendar.events[0] ?? "Sin eventos" : "Conectar Calendar"}</p>
            <div className="mt-3 border-t border-cyan-900/50 pt-2">
              <p className="text-[10px] text-cyan-400/90">➕ Nuevo evento:</p>
              <Field label="Nombre evento"><input className={hudInput} value={calTitle} onChange={(e) => setCalTitle(e.target.value)} /></Field>
              <Field label="Fecha"><input type="date" className={hudInput} value={calDate} onChange={(e) => setCalDate(e.target.value)} /></Field>
              <Field label="Hora"><input type="time" className={hudInput} value={calTime} onChange={(e) => setCalTime(e.target.value)} /></Field>
              <Field label="Recordatorio (min)"><input className={hudInput} value={calReminder} onChange={(e) => setCalReminder(e.target.value)} /></Field>
              {data.calendar.connected ? (
                <HudPopupButton label="GUARDAR EVENTO" onClick={() => void saveCalendar()} />
              ) : (
                <HudPopupButton label="Conectar Calendar" onClick={() => void connectGoogleCalendarFromLife()} />
              )}
            </div>
            <div className="mt-2 border-t border-cyan-900/50 pt-2">
              <HudPopupButton label="Preguntar a CED" onClick={() => { dispatchLifeVoicePrompt("¿qué tengo hoy en mi calendario?"); onClose(); }} />
              <HudPopupButton label="Ver esta semana" onClick={() => { dispatchLifeVoicePrompt("¿qué eventos tengo esta semana?"); onClose(); }} />
            </div>
          </>
        ) : null}

        {active === "events" ? (
          <>
            <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-wider">🔔 EVENTOS Y RECORDATORIOS</p>
            <ul className="mt-2 space-y-1 text-[#00ffff]/90">
              {reminders.length ? reminders.slice(0, 5).map((r) => (
                <li key={r.id}>• {r.date} {r.time} — {r.text}</li>
              )) : <li>• No hay recordatorios</li>}
            </ul>
            <div className="mt-3 border-t border-cyan-900/50 pt-2">
              <Field label="¿Qué recordar?"><input className={hudInput} value={remText} onChange={(e) => setRemText(e.target.value)} /></Field>
              <Field label="Fecha"><input type="date" className={hudInput} value={remDate} onChange={(e) => setRemDate(e.target.value)} /></Field>
              <Field label="Hora"><input type="time" className={hudInput} value={remTime} onChange={(e) => setRemTime(e.target.value)} /></Field>
              <HudPopupButton label="CREAR RECORDATORIO" onClick={saveReminderItem} />
            </div>
            <HudPopupButton label="Preguntar a CED" onClick={() => { dispatchLifeVoicePrompt("¿qué recordatorios tengo?"); onClose(); }} />
          </>
        ) : null}

        {active === "gmail" ? (
          <>
            <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-wider">📧 GMAIL</p>
            <p className="mt-2">{data.gmail.connected ? `${data.gmail.unread_count} emails sin leer` : "Conectar Gmail"}</p>
            <ul className="mt-2 space-y-1 text-[#00ffff]/80">
              {(data.gmail.connected ? data.gmail.messages : ["Conecte Gmail"]).map((line, i) => (
                <li key={`${i}-${line}`}>• {line}</li>
              ))}
            </ul>
            <div className="mt-3 border-t border-cyan-900/50 pt-2">
              <Field label="Para"><input className={hudInput} value={mailTo} onChange={(e) => setMailTo(e.target.value)} /></Field>
              <Field label="Asunto"><input className={hudInput} value={mailSubject} onChange={(e) => setMailSubject(e.target.value)} /></Field>
              <Field label="Mensaje"><textarea className={`${hudInput} min-h-[72px] resize-none`} value={mailBody} onChange={(e) => setMailBody(e.target.value)} /></Field>
              {data.gmail.connected ? (
                <HudPopupButton label="ENVIAR" onClick={() => void sendMail()} />
              ) : (
                <HudPopupButton label="Conectar Gmail" onClick={() => void connectGoogleGmailFromLife()} />
              )}
            </div>
            <HudPopupButton label="Leer emails con CED" onClick={() => { dispatchLifeVoicePrompt("¿tengo emails importantes?"); onClose(); }} />
            <HudPopupButton label="Enviar con CED" onClick={() => { dispatchLifeVoicePrompt("Quiero enviar un email"); onClose(); }} />
          </>
        ) : null}

        {status ? <p className="mt-2 text-center text-[10px] text-cyan-200/90">{status}</p> : null}
      </div>
    </>
  );
}
