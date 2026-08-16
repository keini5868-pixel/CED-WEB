"use client";

import { useCallback, useEffect, useState } from "react";

import {
  fetchTrash,
  purgeFromTrash,
  restoreFromTrash,
  type TrashItem,
  type TrashScope,
} from "@/lib/api/trash";

const SCOPE_LABEL: Record<string, string> = {
  conversation: "Conversación",
  image: "Imagen",
  pdf: "PDF",
  finance: "Finanzas",
};

export function HistorialPapelera({
  scopes,
}: {
  scopes?: TrashScope[];
}) {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (scopes && scopes.length === 1) {
        setItems(await fetchTrash(scopes[0]));
      } else {
        const all = await fetchTrash();
        setItems(
          scopes ? all.filter((i) => scopes.includes(i.scope)) : all,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la papelera.");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [scopes]);

  useEffect(() => {
    void load();
  }, [load]);

  async function restore(item: TrashItem) {
    setBusyId(item.id);
    try {
      await restoreFromTrash(item.scope, [item.id]);
      setItems((prev) => prev.filter((x) => x.id !== item.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo restaurar.");
    } finally {
      setBusyId(null);
    }
  }

  async function purge(item: TrashItem) {
    if (!window.confirm("¿Borrar definitivamente? Esto no se puede deshacer.")) {
      return;
    }
    setBusyId(item.id);
    try {
      await purgeFromTrash(item.scope, [item.id]);
      setItems((prev) => prev.filter((x) => x.id !== item.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) {
    return <p className="ced-hud-text-muted text-sm">Cargando papelera…</p>;
  }

  return (
    <div className="space-y-3">
      <p className="ced-hud-text-muted text-xs">
        Los elementos se eliminan solos a los 30 días. Puede restaurarlos o
        borrarlos ahora.
      </p>
      {error ? (
        <p className="rounded border border-red-500/40 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      {items.length === 0 ? (
        <p className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-sm">
          La papelera está vacía.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={`${item.scope}-${item.id}`}
              className="rounded border border-cyan-900/50 bg-[#0a0a0a] p-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-wider text-cyan-600">
                    {SCOPE_LABEL[item.scope] || item.scope}
                  </p>
                  <p className="truncate text-sm text-cyan-100">{item.title}</p>
                  {item.purge_after ? (
                    <p className="ced-hud-text-muted mt-1 text-[10px]">
                      Se borra el{" "}
                      {new Date(item.purge_after).toLocaleDateString("es-MX")}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    disabled={busyId === item.id}
                    onClick={() => void restore(item)}
                    className="text-[10px] uppercase tracking-wider text-emerald-300 hover:text-emerald-100 disabled:opacity-40"
                  >
                    Restaurar
                  </button>
                  <button
                    type="button"
                    disabled={busyId === item.id}
                    onClick={() => void purge(item)}
                    className="text-[10px] uppercase tracking-wider text-rose-300 hover:text-rose-100 disabled:opacity-40"
                  >
                    Borrar ya
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
