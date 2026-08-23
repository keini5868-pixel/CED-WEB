"use client";

import { useCallback, useEffect, useState } from "react";

import { CedButton } from "@ced/ui";

import { AdminCreateUserModal } from "@/components/admin/AdminCreateUserModal";
import { AdminUserSuccessModal } from "@/components/admin/AdminUserSuccessModal";
import {
  ACCESS_TYPE_LABELS,
  STATUS_LABELS,
} from "@/components/admin/adminUserUtils";
import {
  creditAdminRecharge,
  fetchAdminUsers,
  type AdminUserRow,
  type CreateAdminUserResult,
} from "@/lib/api/admin";

function statusBadge(status: string): string {
  if (status === "active") return "text-emerald-400";
  if (status === "trial") return "text-sky-400";
  if (status === "expiring") return "text-amber-400";
  if (status === "paused" || status === "expired" || status === "past_due") {
    return "text-red-400";
  }
  return "text-cyan-400/70";
}

function formatExpiry(iso: string | null, isTrial?: boolean): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const days = Math.ceil((d.getTime() - Date.now()) / 86400000);
    const dateLabel = d.toLocaleDateString("es-MX", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    if (days < 0) return `Expirado · ${dateLabel}`;
    if (isTrial) {
      return days <= 1 ? `Trial · hoy (${dateLabel})` : `Trial · ${days}d (${dateLabel})`;
    }
    if (days <= 7) return `${days}d · ${dateLabel}`;
    return dateLabel;
  } catch {
    return "—";
  }
}

function planCell(u: AdminUserRow): string {
  if (u.plan_label) return u.plan_label;
  if (u.is_trial) return `Trial · ${u.plan ?? "Élite"}`;
  if (u.plan === "free_basic") return "CED Básico Gratis";
  if (!u.plan) return "—";
  return u.plan.replace("elite_", "");
}

export function AdminUsersPanel() {
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [expiringCount, setExpiringCount] = useState(0);
  const [trialCount, setTrialCount] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [crediting, setCrediting] = useState<string | null>(null);

  const load = useCallback(async (q = search) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminUsers(q);
      setUsers(data.users);
      setTotal(data.total);
      setActiveCount(data.active_count);
      setExpiringCount(data.expiring_count);
      setTrialCount(data.trial_count ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCredit = async (user: AdminUserRow) => {
    const ok = window.confirm(
      `¿Acreditar recarga de $10 a ${user.email}? Quedarán ≈ $6 / 60 min extra. Úsalo si Stripe cobró y aquí no aparece.`,
    );
    if (!ok) return;
    setCrediting(user.id);
    setError(null);
    try {
      await creditAdminRecharge(user.id, 10);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo acreditar");
    } finally {
      setCrediting(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <CedButton type="button" onClick={() => setCreateOpen(true)}>
            ➕ AGREGAR USUARIO MANUAL
          </CedButton>
          <CedButton
            variant="secondary"
            type="button"
            disabled={loading}
            onClick={() => void load()}
          >
            ↻ Refresh
          </CedButton>
        </div>
        <div className="flex flex-1 flex-wrap items-center gap-2 sm:max-w-md sm:justify-end">
          <input
            type="search"
            placeholder="Buscar nombre o email…"
            className="min-w-[180px] flex-1 rounded border border-cyan-500/40 bg-black/60 px-3 py-2 text-sm text-cyan-50"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <button
            type="button"
            className="rounded border border-cyan-600/60 px-3 py-2 text-xs text-cyan-400"
            onClick={handleSearch}
          >
            Buscar
          </button>
        </div>
      </div>

      <p className="ced-hud-text-muted text-xs">
        Total: {total} usuarios · {activeCount} activos
        {trialCount > 0 ? ` · ${trialCount} en trial` : ""}
        {expiringCount > 0 ? ` · ${expiringCount} expirando pronto` : ""}
      </p>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <div className="overflow-x-auto rounded border border-cyan-500/25">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-cyan-500/20 bg-black/50 text-[10px] uppercase tracking-widest text-cyan-500">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Nombre / Email</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Plan</th>
              <th className="px-3 py-2">Uso / quedan</th>
              <th className="px-3 py-2">Recarga</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2">Expira</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-cyan-600">
                  Cargando usuarios…
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-cyan-600">
                  No hay usuarios. Crea el primero con el botón de arriba.
                </td>
              </tr>
            ) : (
              users.map((u, i) => (
                <tr
                  key={u.id}
                  className="border-b border-cyan-500/10 hover:bg-cyan-500/5"
                >
                  <td className="px-3 py-2 text-cyan-600">{i + 1}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-cyan-100">
                      {u.full_name || "—"}
                    </div>
                    <div className="text-xs text-cyan-500/80">{u.email}</div>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {ACCESS_TYPE_LABELS[u.access_type] ?? u.access_type}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <div className="text-cyan-100">{planCell(u)}</div>
                    {u.is_trial ? (
                      <div className="text-[10px] text-sky-400/90">
                        No es plan pagado · prueba de voz
                      </div>
                    ) : u.is_paid ? (
                      <div className="text-[10px] text-emerald-400/80">
                        Suscripción confirmada
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs text-cyan-400/80">
                    <div>
                      {(u.used_minutes ?? 0).toFixed(1)} /{" "}
                      {(u.total_available_minutes ?? u.minutes_daily ?? 0).toFixed(0)} min
                    </div>
                    <div className="text-[10px] text-cyan-500/80">
                      Quedan {(u.remaining_minutes ?? 0).toFixed(0)} min
                      {u.is_trial ? " (prueba)" : " hoy"}
                    </div>
                    {u.bonus_minutes ? (
                      <div className="text-[10px] text-emerald-400/80">
                        Plan {u.minutes_daily ?? 0} + recarga{" "}
                        {u.bonus_minutes.toFixed(0)}
                      </div>
                    ) : u.is_trial ? (
                      <div className="text-[10px] text-sky-400/80">
                        {u.minutes_daily ?? 0} min de prueba
                      </div>
                    ) : (
                      <div className="text-[10px] text-cyan-600">
                        {u.minutes_daily ?? 0} min/día del plan
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {(u.recharge_balance_usd ?? 0) > 0 ? (
                      <>
                        <div className="text-emerald-300">
                          ${Number(u.recharge_balance_usd).toFixed(2)}
                        </div>
                        <div className="text-[10px] text-emerald-500/80">
                          ≈ {Number(u.bonus_minutes ?? 0).toFixed(0)} min extra
                        </div>
                      </>
                    ) : (
                      <span className="text-cyan-700">$0.00</span>
                    )}
                    {(u.last_recharge_usd ?? 0) > 0 ? (
                      <div className="mt-0.5 text-[10px] text-cyan-400/80">
                        Pagó ${Number(u.last_recharge_usd).toFixed(0)}
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="mt-1 block text-[10px] text-amber-400 underline disabled:opacity-40"
                        disabled={crediting === u.id}
                        onClick={() => void handleCredit(u)}
                      >
                        {crediting === u.id ? "…" : "Acreditar $10"}
                      </button>
                    )}
                  </td>
                  <td className={`px-3 py-2 text-xs ${statusBadge(u.status)}`}>
                    {u.status === "active"
                      ? "✅"
                      : u.status === "trial"
                        ? "🧪"
                        : u.status === "expiring"
                          ? "⏰"
                          : "⏸"}{" "}
                    {STATUS_LABELS[u.status] ?? u.status}
                  </td>
                  <td className="px-3 py-2 text-xs text-cyan-400/80">
                    {formatExpiry(u.expires_at, u.is_trial)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <AdminCreateUserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(result) => {
          setSuccessResult(result);
          void load();
        }}
      />
      <AdminUserSuccessModal
        result={successResult}
        onClose={() => setSuccessResult(null)}
      />
    </div>
  );
}
