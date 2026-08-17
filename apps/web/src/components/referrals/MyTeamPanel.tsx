"use client";

import { useCallback, useEffect, useState } from "react";

import {
  addPmPartner,
  fetchMyTeam,
  savePmProfile,
  type MyTeamResponse,
  type ReferralGuest,
  type ReferralGuestStatus,
} from "@/lib/api/referrals";

const STATUS_LABEL: Record<ReferralGuestStatus, string> = {
  active: "Trabajando",
  idle: "Inactivo",
  unused: "Sin uso de venta",
  pending: "Pendiente de registro",
};

function statusClass(status: ReferralGuestStatus): string {
  if (status === "active") return "text-emerald-300";
  if (status === "idle") return "text-amber-300";
  if (status === "pending") return "text-[var(--ced-cyan)]";
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
    <tr className="border-t border-[var(--studio-border)]">
      <td className="px-3 py-2 text-[var(--studio-chat-fg)]">
        {guest.full_name || guest.display_name}
      </td>
      <td className="px-3 py-2 text-[var(--ced-text-muted)]">{guest.email || "—"}</td>
      <td className="px-3 py-2 font-mono tracking-wider text-[var(--ced-cyan)]">
        {guest.ced_id || "—"}
      </td>
      <td className="px-3 py-2 text-[var(--ced-text-muted)]">
        {formatWhen(guest.joined_at)}
      </td>
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

const fieldClass =
  "w-full rounded-lg border border-[var(--studio-border)] bg-[var(--studio-composer-bg)] px-3 py-2 text-sm text-[var(--studio-composer-fg)] placeholder:text-[var(--studio-hint)] focus:border-[var(--ced-cyan)] focus:outline-none";

export function MyTeamPanel() {
  const [data, setData] = useState<MyTeamResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "link" | null>(null);
  const [onboardingName, setOnboardingName] = useState("");
  const [onboardingCed, setOnboardingCed] = useState("");
  const [onboardingBusy, setOnboardingBusy] = useState(false);
  const [partnerName, setPartnerName] = useState("");
  const [partnerEmail, setPartnerEmail] = useState("");
  const [partnerCed, setPartnerCed] = useState("");
  const [partnerBusy, setPartnerBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const next = await fetchMyTeam();
      setData(next);
      setOnboardingName((prev) => prev || next.me?.full_name || "");
      setPartnerCed((prev) => prev || next.referral_code || "");
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

  async function submitOnboarding(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setOnboardingBusy(true);
    try {
      const next = await savePmProfile({
        full_name: onboardingName.trim(),
        sponsor_ced_id: onboardingCed.trim(),
      });
      setData(next);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "No se pudo guardar tu ficha.");
    } finally {
      setOnboardingBusy(false);
    }
  }

  async function submitPartner(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setPartnerBusy(true);
    try {
      const next = await addPmPartner({
        full_name: partnerName.trim(),
        email: partnerEmail.trim(),
        ced_id: partnerCed.trim() || data?.referral_code || "",
      });
      setData(next);
      setPartnerName("");
      setPartnerEmail("");
      setPartnerCed(next.referral_code || partnerCed);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "No se pudo añadir el socio.");
    } finally {
      setPartnerBusy(false);
    }
  }

  const needsOnboarding = Boolean(data?.me?.needs_onboarding);

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6">
      <div>
        <h1 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wide text-[var(--ced-text-primary)] sm:text-xl">
          Estructura PM
        </h1>
        <p className="mt-1 text-sm text-[var(--ced-text-muted)]">
          Cada socio entra con correo, nombre completo e ID de CED. Desde ahí
          crece su negocio: comparte tu enlace o añade socios a tu estructura.
        </p>
      </div>

      {needsOnboarding ? (
        <section className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-card)] p-4">
          <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-[var(--ced-cyan)]">
            TUS DATOS DE ENTRADA
          </h2>
          <p className="mt-1 mb-3 text-xs text-[var(--ced-text-muted)]">
            Antes de usar la estructura, guarda tu correo, nombre completo e ID
            de CED del socio que te invita.
          </p>
          <form onSubmit={(e) => void submitOnboarding(e)} className="grid gap-3 sm:grid-cols-2">
            <label className="block text-[11px] uppercase tracking-wider text-[var(--studio-hint)]">
              Correo
              <input
                className={`${fieldClass} mt-1 opacity-80`}
                type="email"
                value={data?.me?.email || ""}
                readOnly
              />
            </label>
            <label className="block text-[11px] uppercase tracking-wider text-[var(--studio-hint)]">
              Nombre completo
              <input
                className={`${fieldClass} mt-1`}
                name="full_name"
                value={onboardingName}
                onChange={(e) => setOnboardingName(e.target.value)}
                required
                minLength={3}
                placeholder="Nombre y apellidos"
              />
            </label>
            <label className="block text-[11px] uppercase tracking-wider text-[var(--studio-hint)] sm:col-span-2">
              ID de CED
              <input
                className={`${fieldClass} mt-1 font-mono tracking-wider`}
                name="sponsor_ced_id"
                value={onboardingCed}
                onChange={(e) => setOnboardingCed(e.target.value.toUpperCase())}
                placeholder="Ej. CED7A3F2C — el ID de quien te invita"
              />
            </label>
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={onboardingBusy}
                className="rounded-lg border border-[var(--ced-cyan)]/50 bg-[var(--ced-cyan)]/15 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/25 disabled:opacity-50"
              >
                {onboardingBusy ? "Guardando…" : "Guardar y entrar"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-card)] p-4">
        <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-[var(--ced-cyan)]">
          TU ID DE CED
        </h2>
        {data ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded border border-[var(--studio-border)] bg-[var(--studio-composer-bg)] px-3 py-1.5 font-mono text-sm tracking-widest text-[var(--ced-cyan)]">
              {data.referral_code || "—"}
            </code>
            <button
              type="button"
              className="rounded px-2 py-1 text-[10px] uppercase tracking-wider text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10"
              onClick={() => void copy("code", data.referral_code)}
              disabled={!data.referral_code}
            >
              {copied === "code" ? "Copiado" : "Copiar ID"}
            </button>
            <button
              type="button"
              className="rounded px-2 py-1 text-[10px] uppercase tracking-wider text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10"
              onClick={() => void copy("link", data.invite_url)}
              disabled={!data.invite_url}
            >
              {copied === "link" ? "Enlace copiado" : "Copiar enlace"}
            </button>
          </div>
        ) : (
          <p className="mt-2 text-xs text-[var(--studio-hint)]">Cargando…</p>
        )}
        {data?.invite_url ? (
          <p className="mt-2 break-all text-[11px] text-[var(--ced-text-muted)]">
            {data.invite_url}
          </p>
        ) : null}
        <p className="mt-3 text-xs text-[var(--ced-text-muted)]">
          Comparte el enlace o el ID. Quien se registre entra con su correo,
          nombre completo e ID de CED, y queda guardado en tu estructura.
        </p>
      </section>

      <section className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-card)] p-4">
        <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-[var(--ced-cyan)]">
          AÑADIR SOCIO
        </h2>
        <p className="mt-1 mb-3 text-xs text-[var(--ced-text-muted)]">
          Si entra en persona, apunta aquí su correo, nombre completo e ID de
          CED. También puedes esperar a que use tu enlace.
        </p>
        <form onSubmit={(e) => void submitPartner(e)} className="grid gap-3 sm:grid-cols-3">
          <label className="block text-[11px] uppercase tracking-wider text-[var(--studio-hint)]">
            Nombre completo
            <input
              className={`${fieldClass} mt-1`}
              name="partner_full_name"
              value={partnerName}
              onChange={(e) => setPartnerName(e.target.value)}
              required
              minLength={3}
              placeholder="Nombre y apellidos"
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wider text-[var(--studio-hint)]">
            Correo
            <input
              className={`${fieldClass} mt-1`}
              type="email"
              name="partner_email"
              value={partnerEmail}
              onChange={(e) => setPartnerEmail(e.target.value)}
              required
              placeholder="socio@correo.com"
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wider text-[var(--studio-hint)]">
            ID de CED
            <input
              className={`${fieldClass} mt-1 font-mono tracking-wider`}
              name="partner_ced_id"
              value={partnerCed}
              onChange={(e) => setPartnerCed(e.target.value.toUpperCase())}
              required
              placeholder="Tu ID de CED"
            />
          </label>
          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={partnerBusy || needsOnboarding}
              className="rounded-lg border border-[var(--ced-cyan)]/50 bg-[var(--ced-cyan)]/15 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/25 disabled:opacity-50"
            >
              {partnerBusy ? "Guardando…" : "Guardar socio"}
            </button>
          </div>
        </form>
      </section>

      {formError ? <p className="text-sm text-red-400">{formError}</p> : null}

      {data ? (
        <section className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {[
            ["Total", data.counts.total, "text-[var(--studio-chat-fg)]"],
            ["Trabajando", data.counts.active, "text-emerald-300"],
            ["Inactivos", data.counts.idle, "text-amber-300"],
            ["Sin uso", data.counts.unused, "text-[var(--studio-hint)]"],
            ["Pendientes", data.counts.pending ?? 0, "text-[var(--ced-cyan)]"],
          ].map(([label, value, klass]) => (
            <div
              key={String(label)}
              className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-card)] px-3 py-2"
            >
              <p className="text-[10px] uppercase tracking-wider text-[var(--studio-hint)]">
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

      <section className="overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-card)]">
        <table className="min-w-full text-left text-xs text-[var(--studio-chat-fg)]">
          <thead className="font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-[var(--studio-hint)]">
            <tr>
              <th className="px-3 py-2">Nombre completo</th>
              <th className="px-3 py-2">Correo</th>
              <th className="px-3 py-2">ID de CED</th>
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
                <td colSpan={9} className="px-3 py-6 text-center text-[var(--studio-hint)]">
                  {data
                    ? "Aún no hay socios. Comparte tu enlace o añade uno con correo, nombre e ID de CED."
                    : "Cargando socios…"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <p className="text-[11px] leading-relaxed text-[var(--ced-text-muted)]">
        <span className="text-[var(--ced-cyan)]">Qué cuenta:</span> voz (sobre todo en
        contexto PM/FitLine); chat para vender o prospectar; módulo Finanzas /
        plan de acción; ficha de Oportunidades o enlace propio de patrocinio.
        Así ves a quién mentorizar porque todavía no está usando CED como
        herramienta de venta.
      </p>
    </div>
  );
}
