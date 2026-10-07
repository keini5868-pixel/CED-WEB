"use client";

import { useEffect, useState } from "react";

import { HudPanel } from "@ced/ui";

import {
  fetchAdminToolFunds,
  type AdminToolFund,
  type AdminToolFundsResult,
} from "@/lib/api/admin";

const FUND_LABEL: Record<AdminToolFund["funds"], string> = {
  ok: "Con fondos / clave ok",
  low: "Bajo",
  missing: "Falta clave",
  unknown: "Revisa el panel",
};

export default function AdminHerramientasPage() {
  const [data, setData] = useState<AdminToolFundsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchAdminToolFunds()
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="space-y-6 p-4">
      <HudPanel title="HERRAMIENTAS · SOLO ADMIN">
        <p className="ced-hud-text-body max-w-3xl">
          Lo que CED usa por detrás: si hay clave, si falta, y dónde ver saldo y
          fecha de factura. Los clientes no ven esta página.
        </p>
        {data?.note ? (
          <p className="ced-hud-text-muted mt-2 text-xs">{data.note}</p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
      </HudPanel>

      <div className="grid gap-4 md:grid-cols-2">
        {(data?.tools || []).map((tool) => (
          <HudPanel key={tool.id} title={tool.label.toUpperCase()}>
            <p className="text-xs uppercase tracking-widest text-cyan-400/80">
              {FUND_LABEL[tool.funds]}
            </p>
            <p className="mt-2 text-sm text-cyan-100">{tool.use}</p>
            <p className="ced-hud-text-body mt-2">{tool.summary}</p>
            <p className="ced-hud-text-muted mt-2 text-xs">{tool.billing_note}</p>
            <a
              href={tool.billing_url}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block text-sm text-cyan-300 underline decoration-cyan-700 underline-offset-4 hover:text-cyan-100"
            >
              Abrir facturación
            </a>
          </HudPanel>
        ))}
      </div>
    </div>
  );
}
