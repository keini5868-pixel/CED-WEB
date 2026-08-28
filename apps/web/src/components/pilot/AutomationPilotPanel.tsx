"use client";

import { Loader2, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  confirmAutomationPreview,
  ensureAutomationCard,
  fetchAutomationCards,
  fetchAutomationStatus,
  previewAutomationSpeech,
  setAutomationStatus,
  type AutomationCard,
  type AutomationStatus,
} from "@/lib/api/automationPilot";
import type { ModulePanelProps } from "@/modules/types";

const CHANNEL_LABEL: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  whatsapp: "WhatsApp",
};

/** Panel piloto — embudo narrado + tarjetas curadas (sin canvas). */
export function AutomationModuleContent(_props: ModulePanelProps) {
  const [status, setStatus] = useState<AutomationStatus | null>(null);
  const [cards, setCards] = useState<AutomationCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [speech, setSpeech] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [st, list] = await Promise.all([
        fetchAutomationStatus(),
        fetchAutomationCards(),
      ]);
      setStatus(st);
      setCards(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar Automatización");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onToggle(card: AutomationCard) {
    setError(null);
    setMessage(null);
    try {
      if (!card.id) {
        if (!card.card_key) return;
        const created = await ensureAutomationCard(card.card_key, true);
        if (!created.ok) {
          setError(created.error || "No se pudo activar");
          return;
        }
        setMessage(`Activada: ${card.name}`);
      } else {
        const next = card.status === "active" ? "paused" : "active";
        const res = await setAutomationStatus(card.id, next);
        if (!res.ok) {
          setError(res.error || "No se pudo cambiar el estado");
          return;
        }
        setMessage(next === "active" ? `Activada: ${card.name}` : `En pausa: ${card.name}`);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al actualizar");
    }
  }

  async function onPreview() {
    setError(null);
    setMessage(null);
    setPreview(null);
    try {
      const res = await previewAutomationSpeech(speech);
      if (!res.ok || !res.preview) {
        setError(res.error || "No reconocí la automatización");
        return;
      }
      setPreview(res.preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al interpretar");
    }
  }

  async function onConfirm(activate: boolean) {
    if (!preview) return;
    setError(null);
    try {
      const res = await confirmAutomationPreview(preview, activate);
      if (!res.ok) {
        setError(res.error || "No se pudo guardar");
        return;
      }
      setMessage(res.message || "Guardado");
      setPreview(null);
      setSpeech("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al confirmar");
    }
  }

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto px-1 pb-6 text-[14px] text-slate-200">
      <header className="space-y-2">
        <div className="flex items-center gap-2 text-cyan-100">
          <Workflow className="h-5 w-5 opacity-80" />
          <h2 className="text-base font-semibold tracking-wide">Automatización</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-slate-400">
          Embudo Instagram → Facebook → WhatsApp. Describe a CED lo que quieres; sin
          canvas ni nodos técnicos.
        </p>
        {status?.dry_run ? (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100/90">
            Modo prueba (dry-run): se registran eventos IG/FB pero no se envían
            respuestas reales hasta Advanced Access de Meta.
          </p>
        ) : null}
      </header>

      <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-cyan-950/40 to-black/40 px-4 py-3">
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-cyan-300/80">
          Tu recorrido
        </h3>
        {busy && !status ? (
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
          </div>
        ) : (
          <p className="leading-relaxed text-slate-200">
            {status?.narrative || "Aún no hay actividad registrada en el embudo."}
          </p>
        )}
        {status ? (
          <p className="mt-2 text-[12px] text-slate-500">
            Activas {status.active_count}
            {status.active_cap >= 0 ? ` / ${status.active_cap}` : " (sin límite)"}
          </p>
        ) : null}
      </section>

      <section className="space-y-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
          Dile a CED qué automatizar
        </h3>
        <textarea
          value={speech}
          onChange={(e) => setSpeech(e.target.value)}
          rows={3}
          placeholder='Ej. Cuando alguien comente "info" en mis reels, responde con el link de WhatsApp'
          className="w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/40 focus:outline-none"
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onPreview()}
            disabled={!speech.trim()}
            className="rounded-lg bg-cyan-600/90 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
          >
            Interpretar
          </button>
          {preview ? (
            <>
              <button
                type="button"
                onClick={() => void onConfirm(true)}
                className="rounded-lg bg-emerald-600/90 px-3 py-1.5 text-sm font-medium text-white"
              >
                Confirmar y activar
              </button>
              <button
                type="button"
                onClick={() => void onConfirm(false)}
                className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-slate-200"
              >
                Guardar en pausa
              </button>
            </>
          ) : null}
        </div>
        {preview ? (
          <p className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[13px] text-cyan-100/90">
            {String(preview.confirmation || JSON.stringify(preview))}
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
          Tarjetas
        </h3>
        <ul className="space-y-2.5">
          {cards.map((card) => {
            const active = card.status === "active";
            const key = card.id || card.card_key || card.name;
            return (
              <li
                key={key}
                className="rounded-xl border border-white/10 bg-black/30 px-3.5 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-slate-100">{card.name}</div>
                    <div className="mt-0.5 text-[12px] text-slate-500">
                      {CHANNEL_LABEL[card.channel] || card.channel}
                    </div>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
                      {card.description}
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={active}
                    onClick={() => void onToggle(card)}
                    className={`relative mt-0.5 h-7 w-12 shrink-0 rounded-full transition ${
                      active ? "bg-emerald-500/80" : "bg-slate-700"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 h-6 w-6 rounded-full bg-white transition ${
                        active ? "left-5" : "left-0.5"
                      }`}
                    />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {status?.meta_scopes_note ? (
        <p className="text-[11px] leading-relaxed text-slate-600">
          {status.meta_scopes_note}
        </p>
      ) : null}
      {message ? (
        <p className="text-[13px] text-emerald-300/90">{message}</p>
      ) : null}
      {error ? <p className="text-[13px] text-rose-300/90">{error}</p> : null}
    </div>
  );
}
