"use client";

import { useCallback, useEffect, useState } from "react";

import { CedButton } from "@ced/ui";

import {
  fetchManyChatStatus,
  rotateManyChatSecret,
  saveManyChatBehavior,
  type ManyChatCtaWhen,
  type ManyChatRole,
  type ManyChatStatus,
  type ManyChatTone,
} from "@/lib/api/manychat";

const ROLES: { id: ManyChatRole; label: string; hint: string }[] = [
  { id: "closer", label: "Cierre", hint: "Pregunta, objeta y manda el grupo cuando esté listo." },
  { id: "qualifier", label: "Calificar", hint: "Solo entiende si encaja. Sin cierre fuerte." },
  { id: "support", label: "Soporte", hint: "Resuelve la duda. Enlace solo si aporta." },
  { id: "custom", label: "Tú lo escribes", hint: "CED sigue solo tu plantilla." },
];

const TONES: { id: ManyChatTone; label: string }[] = [
  { id: "cercano", label: "Cercano" },
  { id: "formal", label: "Formal" },
  { id: "directo", label: "Directo" },
];

const CTA_WHEN: { id: ManyChatCtaWhen; label: string }[] = [
  { id: "ready", label: "Cuando esté listo" },
  { id: "always", label: "Siempre" },
  { id: "never", label: "Nunca (salvo que lo pida)" },
];

function CopyField({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false);
  return (
    <div>
      <p className="mb-1 font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.22em] text-cyan-500">
        {label}
      </p>
      <div className="flex gap-2">
        <input
          readOnly
          value={value}
          className="min-w-0 flex-1 rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-xs text-cyan-100"
        />
        <CedButton
          type="button"
          variant="ghost"
          className="shrink-0"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setDone(true);
              window.setTimeout(() => setDone(false), 1600);
            } catch {
              setDone(false);
            }
          }}
        >
          {done ? "Copiado" : "Copiar"}
        </CedButton>
      </div>
    </div>
  );
}

export function ManyChatAutomationPanel() {
  const [status, setStatus] = useState<ManyChatStatus | null>(null);
  const [role, setRole] = useState<ManyChatRole>("closer");
  const [tone, setTone] = useState<ManyChatTone>("cercano");
  const [mission, setMission] = useState("");
  const [askLines, setAskLines] = useState("");
  const [objections, setObjections] = useState("");
  const [neverSay, setNeverSay] = useState("");
  const [ctaWhen, setCtaWhen] = useState<ManyChatCtaWhen>("ready");
  const [ctaUrl, setCtaUrl] = useState("");
  const [ctaLabel, setCtaLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((st: ManyChatStatus) => {
    setStatus(st);
    setRole(st.role);
    setTone(st.tone);
    setMission(st.mission);
    setAskLines(st.ask_lines);
    setObjections(st.objections);
    setNeverSay(st.never_say);
    setCtaWhen(st.cta_when);
    setCtaUrl(st.cta_url);
    setCtaLabel(st.cta_label);
  }, []);

  const load = useCallback(async () => {
    const st = await fetchManyChatStatus();
    if (st.error) {
      setError(st.error);
      return;
    }
    apply(st);
  }, [apply]);

  useEffect(() => {
    void load().catch((err: Error) => setError(err.message));
  }, [load]);

  async function persist(nextEnabled?: boolean) {
    setBusy(true);
    setError(null);
    try {
      const st = await saveManyChatBehavior({
        ...(typeof nextEnabled === "boolean" ? { enabled: nextEnabled } : {}),
        role,
        tone,
        mission,
        ask_lines: askLines,
        objections,
        never_say: neverSay,
        cta_when: ctaWhen,
        cta_url: ctaUrl.trim(),
        cta_label: ctaLabel.trim(),
      });
      if (st.error) {
        setError(st.error);
        return;
      }
      apply(st);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar.");
    } finally {
      setBusy(false);
    }
  }

  async function rotate() {
    setBusy(true);
    setError(null);
    try {
      const st = await rotateManyChatSecret();
      if (st.error) {
        setError(st.error);
        return;
      }
      apply(st);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo rotar el secreto.");
    } finally {
      setBusy(false);
    }
  }

  const enabled = Boolean(status?.enabled);
  const allowed = status?.allowed !== false;

  return (
    <div className="ced-hud-page-bg relative flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />

      <header className="flex shrink-0 flex-wrap items-end justify-between gap-4 border-b border-cyan-500/20 px-4 py-5 sm:px-8">
        <div>
          <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.38em] text-cyan-400">
            SISTEMA · AUTOMATIZACIÓN
          </p>
          <h1 className="mt-1 font-[family-name:var(--font-orbitron)] text-2xl text-cyan-50 sm:text-4xl">
            ManyChat + CED
          </h1>
          <p className="mt-2 max-w-2xl font-sans text-sm tracking-normal text-cyan-200/80">
            Primero llena la plantilla y el enlace del grupo. Guarda. Luego
            Activa CED. ManyChat lo hacemos después, cuando yo te diga.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={[
              "rounded-full border px-3 py-1 text-xs",
              enabled
                ? "border-cyan-400/60 bg-cyan-400/15 text-cyan-100"
                : "border-white/15 text-cyan-300/70",
            ].join(" ")}
          >
            {enabled ? "Canal activo" : "Canal en pausa"}
          </span>
          <CedButton
            type="button"
            disabled={busy || !status}
            onClick={() => void persist(!enabled)}
          >
            {enabled ? "Pausar" : "Activar CED"}
          </CedButton>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-8">
        {error ? (
          <p className="rounded-lg border border-red-400/40 bg-red-950/40 px-3 py-2 font-sans text-sm tracking-normal text-red-100">
            {error}
          </p>
        ) : null}
        {!allowed ? (
          <p className="rounded-lg border border-amber-400/30 bg-amber-950/30 px-3 py-2 text-sm text-amber-100">
            Puedes armar la plantilla. Para encender el canal hace falta plan Pro,
            Élite, Founding o Cierre.
          </p>
        ) : null}

        <section className="rounded-2xl border border-cyan-500/20 bg-black/30 p-5">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.18em] text-cyan-200">
            1. Plantilla
          </h2>
          <p className="mt-2 font-sans text-sm tracking-normal text-cyan-200/80">
            Cómo quieres que CED hable en los DM. Llena los recuadros y baja a
            guardar.
          </p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {ROLES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setRole(item.id);
                  const preset = status?.presets?.[item.id];
                  if (preset && !mission.trim()) setMission(preset.mission);
                }}
                className={[
                  "rounded-xl border px-3 py-3 text-left",
                  role === item.id
                    ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-50"
                    : "border-cyan-900/60 text-cyan-200 hover:border-cyan-600",
                ].join(" ")}
              >
                <span className="block text-sm font-medium">{item.label}</span>
                <span className="mt-1 block text-xs text-cyan-300/70">{item.hint}</span>
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {TONES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTone(item.id)}
                className={[
                  "rounded-full border px-3 py-1 text-xs",
                  tone === item.id
                    ? "border-cyan-400/70 bg-cyan-400/15 text-cyan-50"
                    : "border-cyan-900/70 text-cyan-300",
                ].join(" ")}
              >
                {item.label}
              </button>
            ))}
          </div>
          <label className="mt-4 block">
            <span className="mb-1 block text-[10px] tracking-[0.2em] text-cyan-500">
              CÓMO DEBE COMPORTARSE
            </span>
            <textarea
              value={mission}
              onChange={(e) => setMission(e.target.value)}
              rows={4}
              placeholder="Ej. Pregunta qué busca, no inventes precios, cierra hacia el grupo cuando pida el siguiente paso."
              className="w-full rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50"
            />
          </label>
          <label className="mt-3 block">
            <span className="mb-1 block text-[10px] tracking-[0.2em] text-cyan-500">
              PREGUNTAS (UNA POR LÍNEA)
            </span>
            <textarea
              value={askLines}
              onChange={(e) => setAskLines(e.target.value)}
              rows={3}
              placeholder={"¿Qué te interesa?\n¿De dónde nos escribes?"}
              className="w-full rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50"
            />
          </label>
          <label className="mt-3 block">
            <span className="mb-1 block text-[10px] tracking-[0.2em] text-cyan-500">
              CÓMO TRATAR OBJECIONES
            </span>
            <textarea
              value={objections}
              onChange={(e) => setObjections(e.target.value)}
              rows={3}
              placeholder="Responde en una frase y vuelve a preguntar. Si pide un humano, avisa."
              className="w-full rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50"
            />
          </label>
          <label className="mt-3 block">
            <span className="mb-1 block text-[10px] tracking-[0.2em] text-cyan-500">
              NUNCA DIGAS
            </span>
            <textarea
              value={neverSay}
              onChange={(e) => setNeverSay(e.target.value)}
              rows={2}
              placeholder="No inventes precios. No prometas ingresos. No pidas teléfono en el DM."
              className="w-full rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50"
            />
          </label>
        </section>

        <section className="rounded-2xl border border-cyan-500/20 bg-black/30 p-5">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.18em] text-cyan-200">
            2. Enlace del grupo
          </h2>
          <p className="mt-2 font-sans text-sm tracking-normal text-cyan-200/80">
            Pega el enlace de WhatsApp. CED no inventa un grupo si esto está vacío.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label>
              <span className="mb-1 block text-[10px] tracking-[0.2em] text-cyan-500">
                URL
              </span>
              <input
                value={ctaUrl}
                onChange={(e) => setCtaUrl(e.target.value)}
                placeholder="https://chat.whatsapp.com/..."
                className="w-full rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              />
            </label>
            <label>
              <span className="mb-1 block text-[10px] tracking-[0.2em] text-cyan-500">
                ETIQUETA
              </span>
              <input
                value={ctaLabel}
                onChange={(e) => setCtaLabel(e.target.value)}
                placeholder="Grupo CED"
                className="w-full rounded-lg border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {CTA_WHEN.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setCtaWhen(item.id)}
                className={[
                  "rounded-full border px-3 py-1 text-xs",
                  ctaWhen === item.id
                    ? "border-cyan-400/70 bg-cyan-400/15 text-cyan-50"
                    : "border-cyan-900/70 text-cyan-300",
                ].join(" ")}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="mt-5">
            <CedButton type="button" disabled={busy} onClick={() => void persist()}>
              Guardar plantilla
            </CedButton>
          </div>
        </section>

        <section className="rounded-2xl border border-cyan-500/20 bg-black/30 p-5">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.18em] text-cyan-200">
            ManyChat — después
          </h2>
          <p className="mt-2 font-sans text-sm tracking-normal text-cyan-200/80">
            No copies nada de aquí todavía. Cuando la plantilla esté guardada y
            CED activo, te digo exactamente qué pegar en ManyChat.
          </p>
          <div className="mt-4 grid gap-3">
            <CopyField label="URL del Dynamic Block" value={status?.webhook_url || "…"} />
            <CopyField label="Secreto" value={status?.webhook_secret || "…"} />
          </div>
          <div className="mt-3">
            <CedButton type="button" variant="ghost" disabled={busy} onClick={() => void rotate()}>
              Rotar secreto
            </CedButton>
          </div>
        </section>

        <section className="rounded-2xl border border-cyan-500/20 bg-black/30 p-5">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.18em] text-cyan-200">
            Actividad reciente
          </h2>
          {(status?.messages || []).length === 0 ? (
            <p className="mt-3 text-sm text-cyan-300/60">
              Cuando ManyChat llame a CED, aquí verás entradas y respuestas de
              esta cuenta.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {(status?.messages || []).map((row) => (
                <li
                  key={row.id}
                  className="rounded-lg border border-cyan-900/50 bg-black/40 px-3 py-2 text-sm text-cyan-100"
                >
                  <span className="mr-2 text-[10px] uppercase tracking-widest text-cyan-500">
                    {row.direction === "out" ? "CED" : "DM"}
                  </span>
                  {row.body}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
