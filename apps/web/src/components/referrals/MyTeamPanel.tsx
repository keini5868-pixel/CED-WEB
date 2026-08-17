"use client";

import { useCallback, useEffect, useState } from "react";

import {
  fetchMyTeam,
  type MyTeamResponse,
  type ReferralGuest,
  type ReferralGuestStatus,
} from "@/lib/api/referrals";

const STATUS_LABEL: Record<ReferralGuestStatus, string> = {
  active: "Trabajando",
  idle: "Inactivo",
  unused: "Sin uso de venta",
};

function statusClass(status: ReferralGuestStatus): string {
  if (status === "active") return "text-emerald-300";
  if (status === "idle") return "text-amber-300";
  return "text-cyan-600";
}

function mark(used: boolean, extra?: string): string {
  if (!used) return "—";
  return extra ? `Sí · ${extra}` : "Sí";
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleDateString("es", {
    day: "2-digit",
    month: "short",
  });
}

function GuestRow({ guest }: { guest: ReferralGuest }) {
  const voiceExtra = guest.signals.voice.pm_context
    ? "PM"
    : guest.signals.voice.minutes_14d > 0
      ? `${guest.signals.voice.minutes_14d} min`
      : undefined;
  const oppsExtra = guest.signals.opps.own_sponsor
    ? "enlace propio"
    : guest.signals.opps.viewed_ficha
      ? "ficha"
      : undefined;

  return (
    <tr className="border-t border-cyan-500/15">
      <td className="px-3 py-2 text-cyan-100">{guest.display_name}</td>
      <td className="px-3 py-2 text-cyan-400/80">{formatWhen(guest.joined_at)}</td>
      <td className="px-3 py-2">{mark(guest.signals.voice.used, voiceExtra)}</td>
      <td className="px-3 py-2">{mark(guest.signals.chat_sales.used)}</td>
      <td className="px-3 py-2">{mark(guest.signals.finance.used)}</td>
      <td className="px-3 py-2">{mark(guest.signals.opps.used, oppsExtra)}</td>
      <td className={`px-3 py-2 font-semibold ${statusClass(guest.status)}`}>
        {STATUS_LABEL[guest.status]}
      </td>
    </tr>
  );
}

export function MyTeamPanel() {
  const [data, setData] = useState<MyTeamResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "link" | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await fetchMyTeam());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo cargar la estructura PM.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function copy(kind: "code" | "link", value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 1800);
    } catch {
      setCopied(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6">
      <div>
        <h1 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wide text-[var(--ced-text-primary)] sm:text-xl">
          Estructura PM
        </h1>
        <p className="mt-1 text-sm text-[var(--ced-text-muted)]">
          Quién de tu estructura PM usa CED de verdad para vender PM International:
          voz, chat de venta/prospección, Finanzas y Oportunidades. No cuenta
          actividad genérica del sistema.
        </p>
      </div>

      <section className="ced-gold-outline rounded-xl bg-black/40 p-4">
        <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
          TU REFERRAL ID
        </h2>
        {data ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded border border-cyan-400/30 bg-cyan-400/5 px-3 py-1.5 font-mono text-sm tracking-widest text-cyan-200">
              {data.referral_code || "—"}
            </code>
            <button
              type="button"
              className="rounded px-2 py-1 text-[10px] uppercase tracking-wider text-cyan-400 hover:bg-cyan-400/10"
              onClick={() => void copy("code", data.referral_code)}
              disabled={!data.referral_code}
            >
              {copied === "code" ? "Copiado" : "Copiar ID"}
            </button>
            <button
              type="button"
              className="rounded px-2 py-1 text-[10px] uppercase tracking-wider text-cyan-400 hover:bg-cyan-400/10"
              onClick={() => void copy("link", data.invite_url)}
              disabled={!data.invite_url}
            >
              {copied === "link" ? "Enlace copiado" : "Copiar enlace"}
            </button>
          </div>
        ) : (
          <p className="mt-2 text-xs text-cyan-600">Cargando…</p>
        )}
        {data?.invite_url ? (
          <p className="mt-2 break-all text-[11px] text-cyan-500/80">{data.invite_url}</p>
        ) : null}
        <p className="mt-3 text-xs text-cyan-100/55">
          Comparte el enlace o el ID. Cuando se registren, aparecen aquí. Ves
          nombre y señales de uso — no transcripciones ni correo completo.
        </p>
      </section>

      {data ? (
        <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            ["Total", data.counts.total, "text-cyan-200"],
            ["Trabajando", data.counts.active, "text-emerald-300"],
            ["Inactivos", data.counts.idle, "text-amber-300"],
            ["Sin uso", data.counts.unused, "text-cyan-500"],
          ].map(([label, value, klass]) => (
            <div
              key={String(label)}
              className="ced-gold-outline rounded-xl bg-black/30 px-3 py-2"
            >
              <p className="text-[10px] uppercase tracking-wider text-cyan-600">
                {label}
              </p>
              <p className={`font-[family-name:var(--font-orbitron)] text-xl ${klass}`}>
                {value}
              </p>
            </div>
          ))}
        </section>
      ) : null}

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <section className="ced-gold-outline overflow-x-auto rounded-xl bg-black/40">
        <table className="min-w-full text-left text-xs text-cyan-200/80">
          <thead className="font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-cyan-500">
            <tr>
              <th className="px-3 py-2">Invitado</th>
              <th className="px-3 py-2">Alta</th>
              <th className="px-3 py-2">Voz</th>
              <th className="px-3 py-2">Chat venta</th>
              <th className="px-3 py-2">Finanzas</th>
              <th className="px-3 py-2">OPPS</th>
              <th className="px-3 py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {data?.guests.length ? (
              data.guests.map((guest) => <GuestRow key={guest.id} guest={guest} />)
            ) : (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-cyan-600">
                  {data
                    ? "Aún no hay invitados con tu Referral ID."
                    : "Cargando invitados…"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <p className="text-[11px] leading-relaxed text-cyan-100/50">
        <span className="text-cyan-400">Qué cuenta:</span> voz (sobre todo en
        contexto PM/FitLine); chat para vender o prospectar; módulo Finanzas /
        plan de acción; ficha de Oportunidades o enlace propio de patrocinio.
        Así ves a quién mentorizar porque todavía no está usando CED como
        herramienta de venta.
      </p>
    </div>
  );
}
