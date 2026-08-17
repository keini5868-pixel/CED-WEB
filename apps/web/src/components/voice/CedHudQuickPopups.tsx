"use client";

import { useCallback, useEffect, useState } from "react";

import { dispatchLifeChatPrompt } from "@/lib/lifeActions";
import {
  loadRemindersMerged,
  saveReminderWithSync,
  type CedReminder,
} from "@/lib/hud/remindersStorage";
import { useHudLifeData } from "@/hooks/useHudLifeData";

export type HudQuickPopupId = "weather" | "events" | null;

const popupShell =
  "fixed bottom-3 left-3 right-[7rem] z-[1000] min-w-0 max-w-none rounded-lg border border-cyan-400/40 bg-black/95 p-4 text-xs text-[#00ffff] shadow-[0_0_24px_rgba(0,255,255,0.15)] sm:right-[8.5rem] lg:bottom-8 lg:left-1/2 lg:right-auto lg:min-w-[260px] lg:max-w-[320px] lg:-translate-x-1/2";

const hudInput =
  "mt-1 w-full rounded border border-cyan-400/30 bg-cyan-400/5 px-2.5 py-1.5 text-xs text-[#00ffff] outline-none focus:border-cyan-400/60";

const hudBtn =
  "mt-1 w-full cursor-pointer rounded border border-[#00ffff] bg-transparent px-3 py-1.5 text-[11px] text-[#00ffff] transition hover:bg-cyan-400/10 disabled:cursor-not-allowed disabled:opacity-40";

function HudPopupButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button type="button" className={hudBtn} onClick={onClick} disabled={disabled}>
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
  const [remText, setRemText] = useState("");
  const [remDate, setRemDate] = useState("");
  const [remTime, setRemTime] = useState("09:00");

  const reloadReminders = useCallback(() => {
    void loadRemindersMerged().then(setReminders);
  }, []);

  const openLifeChat = (prompt?: string, module?: "weather" | "events") => {
    dispatchLifeChatPrompt(prompt, module);
    onClose();
  };

  useEffect(() => {
    if (!active) return;
    reloadReminders();
    setStatus(null);
  }, [active, reloadReminders]);

  if (!active) return null;

  const { temp, condition } = weatherSummary();
  const reminderReady = Boolean(remText.trim() && remDate);

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
              <HudPopupButton label="Actualizar" onClick={() => void refresh()} />
              <HudPopupButton label="Pregunta" onClick={() => openLifeChat(undefined, "weather")} />
            </div>
          </>
        ) : null}

        {active === "events" ? (
          <>
            <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-wider">🔔 RECORDATORIOS</p>
            <p className="mt-1 text-[10px] text-cyan-400/70">Notas personales</p>
            <ul className="mt-2 space-y-1 text-[#00ffff]/90">
              {reminders.length ? reminders.slice(0, 6).map((r) => (
                <li key={r.id}>• {r.date} {r.time} — {r.text}</li>
              )) : <li>• No hay recordatorios guardados</li>}
            </ul>
            <div className="mt-3 border-t border-cyan-900/50 pt-2">
              <Field label="¿Qué recordar?"><input className={hudInput} value={remText} onChange={(e) => setRemText(e.target.value)} placeholder="Ej. llamar al cliente" /></Field>
              <Field label="Fecha"><input type="date" className={hudInput} value={remDate} onChange={(e) => setRemDate(e.target.value)} /></Field>
              <Field label="Hora"><input type="time" className={hudInput} value={remTime} onChange={(e) => setRemTime(e.target.value)} /></Field>
              <HudPopupButton label="CREAR RECORDATORIO" onClick={saveReminderItem} disabled={!reminderReady} />
            </div>
            <HudPopupButton
              label="Preguntar"
              onClick={() => openLifeChat("¿qué recordatorios tengo?", "events")}
            />
          </>
        ) : null}

        {status ? <p className="mt-2 text-center text-[10px] text-cyan-200/90">{status}</p> : null}
      </div>
    </>
  );
}
