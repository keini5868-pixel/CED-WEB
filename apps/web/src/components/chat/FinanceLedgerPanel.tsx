"use client";

import { useCallback, useEffect, useState } from "react";

import {
  listFinanceTransactions,
  type FinanceTransaction,
} from "@/lib/api/finance";
import { sendToTrash } from "@/lib/api/trash";
import { SelectToolbar, TrashIconButton } from "@/components/trash/TrashControls";
import { HistorialPapelera } from "@/components/trash/HistorialPapelera";

export function FinanceLedgerPanel({ tab }: { tab: "movimientos" | "papelera" }) {
  const [rows, setRows] = useState<FinanceTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await listFinanceTransactions());
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los movimientos.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "movimientos") void load();
  }, [tab, load]);

  async function trashIds(ids: string[]) {
    if (ids.length === 0) return;
    setBusy(true);
    try {
      await sendToTrash("finance", ids);
      setRows((prev) => prev.filter((r) => !ids.includes(r.id)));
      setPicked(new Set());
      setSelecting(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar a la papelera.");
    } finally {
      setBusy(false);
    }
  }

  if (tab === "papelera") {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <HistorialPapelera scopes={["finance"]} />
      </div>
    );
  }

  if (loading) {
    return <p className="px-4 py-3 text-sm text-[var(--studio-hint)]">Cargando movimientos…</p>;
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
      {error ? (
        <p className="mb-2 rounded border border-red-500/40 bg-red-950/30 p-2 text-xs text-red-200">
          {error}
        </p>
      ) : null}
      <SelectToolbar
        selecting={selecting}
        selectedCount={picked.size}
        busy={busy}
        onToggle={() => {
          setSelecting((v) => !v);
          setPicked(new Set());
        }}
        onTrash={() => void trashIds([...picked])}
      />
      {rows.length === 0 ? (
        <p className="text-sm text-[var(--ced-text-muted)]">
          Aún no hay movimientos. Anote un gasto o ingreso en el chat.
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex items-center gap-2 rounded border border-[var(--studio-border)] bg-[var(--studio-card)] px-3 py-2"
            >
              {selecting ? (
                <input
                  type="checkbox"
                  checked={picked.has(row.id)}
                  onChange={() => {
                    setPicked((prev) => {
                      const next = new Set(prev);
                      if (next.has(row.id)) next.delete(row.id);
                      else next.add(row.id);
                      return next;
                    });
                  }}
                />
              ) : null}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-[var(--studio-chat-fg)]">
                  {row.description || row.category || row.type}
                </p>
                <p className="text-[10px] text-[var(--ced-text-muted)]">
                  {row.type} · {row.amount} {row.currency || "USD"}
                  {row.occurred_on ? ` · ${row.occurred_on}` : ""}
                </p>
              </div>
              {selecting ? null : (
                <TrashIconButton
                  disabled={busy}
                  onClick={() => void trashIds([row.id])}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
