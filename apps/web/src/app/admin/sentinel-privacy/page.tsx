"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { HudPanel } from "@ced/ui";

import {
  ensureSentinelPrivacyStripeProducts,
  fetchAdminSentinelPrivacy,
  type AdminSentinelPrivacyOverview,
} from "@/lib/api/admin";

export default function AdminSentinelPrivacyPage() {
  const [data, setData] = useState<AdminSentinelPrivacyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stripeMsg, setStripeMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchAdminSentinelPrivacy());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const syncStripe = async () => {
    setBusy(true);
    setStripeMsg(null);
    try {
      const out = await ensureSentinelPrivacyStripeProducts();
      setStripeMsg(
        out.prices
          ? `Precios Stripe listos: ${Object.entries(out.prices)
              .map(([k, v]) => `${k}=${v}`)
              .join(" · ")}`
          : "OK",
      );
    } catch (err) {
      setStripeMsg(err instanceof Error ? err.message : "Falló Stripe");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 p-4">
      <HudPanel title="SENTINEL PRIVACY · ADMIN">
        <p className="ced-hud-text-body max-w-3xl">
          SKU aparte de Élite/Founding — checkout propio en{" "}
          <Link href="/sentinel-privacy" className="text-cyan-300 underline">
            /sentinel-privacy
          </Link>
          . No confundir con <strong className="font-normal">Centinela Ops</strong> (QA voz/imagen).
        </p>
        {data ? (
          <p className="mt-2 text-xs text-violet-300/90">
            CED Shield en servidor:{" "}
            <strong>{data.shield_enabled ? "ON" : "OFF (kill-switch)"}</strong>
            {" · "}
            Suscripciones en DB: <strong>{data.subscription_count}</strong>
          </p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void syncStripe()}
            className="rounded border border-violet-400/60 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-violet-100 hover:bg-violet-500/15 disabled:opacity-50"
          >
            {busy ? "Stripe…" : "Crear precios Stripe ($12/$29/$79)"}
          </button>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded border border-cyan-500/40 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-cyan-200 hover:bg-cyan-500/10"
          >
            Actualizar
          </button>
          <Link
            href="/shield"
            className="rounded border border-cyan-500/40 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-cyan-200 hover:bg-cyan-500/10"
          >
            Demo Shield
          </Link>
        </div>
        {stripeMsg ? <p className="mt-2 text-xs text-emerald-300">{stripeMsg}</p> : null}
      </HudPanel>

      <div className="grid gap-4 md:grid-cols-3">
        {(data?.plans ?? []).map((plan) => (
          <HudPanel key={plan.id} title={plan.label.toUpperCase()}>
            <p className="font-[family-name:var(--font-orbitron)] text-2xl text-violet-200">
              ${plan.price_usd}
              <span className="text-xs text-violet-500">/mes</span>
            </p>
            <p className="mt-1 text-xs text-cyan-400">{plan.seals_per_month} sellos / mes</p>
            <ul className="ced-hud-text-muted mt-2 space-y-1 text-xs">
              {plan.highlights.slice(0, 3).map((h) => (
                <li key={h}>· {h}</li>
              ))}
            </ul>
          </HudPanel>
        ))}
      </div>

      <HudPanel title="SUSCRIPCIONES RECIENTES">
        {!data?.subscriptions?.length ? (
          <p className="ced-hud-text-muted text-sm">
            Aún no hay filas en <code>sentinel_privacy_subscriptions</code>. Haz un checkout de
            prueba logueado.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-xs text-cyan-100/90">
              <thead className="text-[10px] uppercase tracking-wider text-cyan-500">
                <tr>
                  <th className="py-2 pr-3">Usuario</th>
                  <th className="py-2 pr-3">Plan</th>
                  <th className="py-2 pr-3">Estado</th>
                  <th className="py-2 pr-3">Sellos</th>
                  <th className="py-2">Periodo</th>
                </tr>
              </thead>
              <tbody>
                {data.subscriptions.map((row) => {
                  const uid = String(row.user_id ?? "").slice(0, 8);
                  const used = Number(row.seals_used_in_period ?? 0);
                  const cap = Number(row.seals_per_month ?? 0);
                  return (
                    <tr key={String(row.user_id)} className="border-t border-cyan-900/40">
                      <td className="py-2 pr-3 font-mono">{uid}…</td>
                      <td className="py-2 pr-3">{String(row.plan_id ?? "—")}</td>
                      <td className="py-2 pr-3">{String(row.status ?? "—")}</td>
                      <td className="py-2 pr-3">
                        {used}/{cap}
                      </td>
                      <td className="py-2 text-cyan-600">
                        {row.period_end ? String(row.period_end).slice(0, 10) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </HudPanel>
    </div>
  );
}
