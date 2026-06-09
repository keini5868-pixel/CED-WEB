"use client";

import { CedButton } from "@ced/ui";

import { AdminModalPortal } from "@/components/admin/AdminModalPortal";
import type { CreateAdminUserResult } from "@/lib/api/admin";

type Props = {
  result: CreateAdminUserResult | null;
  onClose: () => void;
};

function formatExpiry(iso: string | null): string {
  if (!iso) return "Sin expiración";
  try {
    return new Date(iso).toLocaleDateString("es-MX", {
      dateStyle: "medium",
    });
  } catch {
    return iso;
  }
}

export function AdminUserSuccessModal({ result, onClose }: Props) {
  if (!result) return null;

  const copyText = [
    "CED — Credenciales de acceso",
    `Email: ${result.email}`,
    `Contraseña: ${result.temporary_password}`,
    `Login: ${result.login_url}`,
    `Expira: ${formatExpiry(result.expires_at)}`,
    `Minutos/día: ${result.minutes_daily}`,
    `Saldo: $${result.initial_balance}`,
  ].join("\n");

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* ignore */
    }
  };

  return (
    <AdminModalPortal>
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg border border-emerald-500/50 bg-[#0a1410] p-5 shadow-[0_0_40px_rgba(16,185,129,0.12)]">
        <h2 className="font-[family-name:var(--font-orbitron)] text-base font-bold text-emerald-300">
          ✅ USUARIO CREADO
        </h2>
        <p className="ced-hud-text-muted mt-1 text-xs">
          Entrega estos datos al usuario de forma segura.
        </p>

        <div className="mt-4 space-y-2 rounded border border-emerald-500/30 bg-black/50 p-4 text-sm text-emerald-100">
          <p>
            <span className="text-emerald-400/80">📧 Email:</span> {result.email}
          </p>
          <p className="flex flex-wrap items-center gap-2">
            <span>
              <span className="text-emerald-400/80">🔑 Contraseña:</span>{" "}
              {result.temporary_password}
            </span>
            <button
              type="button"
              className="text-xs text-cyan-400 underline"
              onClick={() => void copy(result.temporary_password)}
            >
              Copiar
            </button>
          </p>
          <p>
            <span className="text-emerald-400/80">🔗 Login:</span>{" "}
            <a href={result.login_url} className="text-cyan-400 underline">
              {result.login_url}
            </a>
          </p>
          <p>
            <span className="text-emerald-400/80">⏰ Expira:</span>{" "}
            {formatExpiry(result.expires_at)}
          </p>
          <p>
            <span className="text-emerald-400/80">📊 Minutos/día:</span>{" "}
            {result.minutes_daily}
          </p>
          <p>
            <span className="text-emerald-400/80">💰 Saldo:</span> $
            {result.initial_balance.toFixed(2)}
          </p>
          {result.email_sent ? (
            <p className="text-xs text-emerald-400">📨 Email de bienvenida enviado.</p>
          ) : result.email_error ? (
            <p className="text-xs text-amber-400">
              Email no enviado: {result.email_error}
            </p>
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <CedButton
            variant="secondary"
            type="button"
            onClick={() => void copy(copyText)}
          >
            📋 Copiar todo
          </CedButton>
          <CedButton type="button" onClick={onClose}>
            Cerrar
          </CedButton>
        </div>
      </div>
    </div>
    </AdminModalPortal>
  );
}
