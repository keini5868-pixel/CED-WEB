"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { TEAM_PATH } from "@/lib/auth/paths";
import { fetchMyTeam } from "@/lib/api/referrals";

export function ReferralIdCard() {
  const [code, setCode] = useState<string>("");
  const [total, setTotal] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchMyTeam()
      .then((data) => {
        if (cancelled) return;
        setCode(data.referral_code || "");
        setTotal(data.counts.total);
      })
      .catch(() => {
        /* silencioso: la página Estructura PM muestra el error */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rounded-xl border border-cyan-500/25 bg-black/40 p-4">
      <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
        REFERRAL ID
      </h2>
      <p className="mt-1 mb-3 text-xs text-cyan-100/60">
        Comparte tu ID para ver si tus invitados usan voz, chat de venta,
        Finanzas y OPPS para trabajar PM International.
      </p>
      {code ? (
        <code className="rounded border border-cyan-400/30 bg-cyan-400/5 px-3 py-1.5 font-mono text-sm tracking-widest text-cyan-200">
          {code}
        </code>
      ) : (
        <p className="text-xs text-cyan-600">Cargando…</p>
      )}
      <p className="mt-3 text-xs text-cyan-100/55">
        {total == null ? "" : `${total} invitado${total === 1 ? "" : "s"} · `}
        <Link href={TEAM_PATH} className="text-cyan-400 hover:underline">
          Ver Mis invitados
        </Link>
      </p>
    </section>
  );
}
