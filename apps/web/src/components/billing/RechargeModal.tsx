"use client";

import Link from "next/link";
import { useState } from "react";

import {
  PUBLIC_PLANS,
  RECHARGE_MAX_USD,
  RECHARGE_MIN_USD,
  RECHARGE_QUICK_AMOUNTS_USD,
  quoteRecharge,
} from "@ced/types";

import {
  continueWithFreeBasic,
  startRechargeCheckout,
  startSubscriptionCheckout,
} from "@/lib/api/billing";

type RechargeModalProps = {
  open: boolean;
  onClose: () => void;
  planMinutesDaily: number;
  planLabel?: string;
};

export function RechargeModal({
  open,
  onClose,
  planMinutesDaily,
  planLabel = "tu plan",
}: RechargeModalProps) {
  const [busy, setBusy] = useState<number | null>(null);
  const [custom, setCustom] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const customAmount = Number(custom);
  const customValid =
    !Number.isNaN(customAmount) &&
    customAmount >= RECHARGE_MIN_USD &&
    customAmount <= RECHARGE_MAX_USD;
  const customQuote = customValid ? quoteRecharge(customAmount) : null;

  const checkout = async (amount: number) => {
    setError(null);
    setBusy(amount);
    try {
      const url = await startRechargeCheckout(amount);
      if (url) window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al recargar.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded border border-cyan-500/40 bg-[#0a0f14] p-6 shadow-xl">
        <h2 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wider text-cyan-300">
          Se agotó tu tiempo de hoy
        </h2>
        <p className="mt-2 text-sm text-cyan-100/80">
          Ya usaste tus {planMinutesDaily} minutos diarios incluidos en {planLabel}.
          ¿Quieres recargar tiempo extra?
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3">
          {RECHARGE_QUICK_AMOUNTS_USD.map((amount) => {
            const q = quoteRecharge(amount);
            const popular = amount === 40;
            const best = amount === 100;
            return (
              <button
                key={amount}
                type="button"
                disabled={busy !== null}
                onClick={() => void checkout(amount)}
                className="rounded border border-cyan-500/30 bg-black/40 p-3 text-left transition hover:border-cyan-400 disabled:opacity-50"
              >
                <div className="font-[family-name:var(--font-orbitron)] text-xl text-white">
                  ${amount}
                </div>
                <div className="text-xs text-cyan-400">
                  +{q.estimatedExtraHours}h aprox.
                </div>
                {popular && (
                  <div className="mt-1 text-[10px] text-amber-400">POPULAR</div>
                )}
                {best && (
                  <div className="mt-1 text-[10px] text-emerald-400">MEJOR PRECIO</div>
                )}
              </button>
            );
          })}
        </div>

        <div className="mt-4 border-t border-cyan-500/20 pt-4">
          <p className="text-xs text-cyan-500">Monto personalizado (${RECHARGE_MIN_USD}–${RECHARGE_MAX_USD})</p>
          <div className="mt-2 flex gap-2">
            <input
              type="number"
              min={RECHARGE_MIN_USD}
              max={RECHARGE_MAX_USD}
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="Ej. 35"
              className="flex-1 rounded border border-cyan-700/50 bg-black/50 px-3 py-2 text-sm text-white"
            />
            <button
              type="button"
              disabled={!customValid || busy !== null}
              onClick={() => customValid && void checkout(customAmount)}
              className="rounded border border-cyan-400 px-4 py-2 text-xs font-bold text-cyan-300 disabled:opacity-40"
            >
              RECARGAR
            </button>
          </div>
          {customQuote && (
            <p className="mt-1 text-xs text-cyan-600">
              Calculado: ~{customQuote.estimatedExtraHours}h extra
            </p>
          )}
        </div>

        <p className="mt-4 text-xs text-cyan-600">
          El saldo no expira. Es permanente y acumulable.
        </p>

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-cyan-700 px-4 py-2 text-xs text-cyan-400"
          >
            Mañana espero
          </button>
          <Link
            href="/pricing"
            className="rounded border border-cyan-400/50 px-4 py-2 text-xs text-cyan-300"
          >
            Ver planes
          </Link>
        </div>
      </div>
    </div>
  );
}

type TrialExpiredModalProps = {
  open: boolean;
  onClose: () => void;
};

export function TrialExpiredModal({ open, onClose }: TrialExpiredModalProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const subscribe = async (planId: string) => {
    setBusy(planId);
    setError(null);
    try {
      const url = await startSubscriptionCheckout(planId);
      if (url) window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al suscribirse.");
    } finally {
      setBusy(null);
    }
  };

  const freeBasic = async () => {
    setBusy("free");
    setError(null);
    try {
      await continueWithFreeBasic();
      onClose();
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4">
      <div className="w-full max-w-lg rounded border border-amber-500/40 bg-[#0a0f14] p-6">
        <h2 className="font-[family-name:var(--font-orbitron)] text-lg text-amber-300">
          Tu prueba terminó
        </h2>
        <p className="mt-2 text-sm text-cyan-100/80">
          Elige un plan de pago o continúa con el plan Básico gratis (solo chat de texto).
        </p>
        <div className="mt-4 space-y-2">
          {PUBLIC_PLANS.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={busy !== null}
              onClick={() => void subscribe(p.id)}
              className="flex w-full items-center justify-between rounded border border-cyan-500/30 px-4 py-3 text-left hover:border-cyan-400 disabled:opacity-50"
            >
              <span className="text-sm text-white">{p.label}</span>
              <span className="text-cyan-400">${p.priceUsd}/mes</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void freeBasic()}
          className="mt-4 w-full rounded border border-cyan-700/50 py-2 text-xs text-cyan-500"
        >
          Continuar con plan Básico gratis
        </button>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </div>
    </div>
  );
}
