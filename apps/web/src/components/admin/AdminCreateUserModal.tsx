"use client";

import { useCallback, useEffect, useState } from "react";

import { CedButton } from "@ced/ui";

import {
  createAdminUser,
  type CreateAdminUserPayload,
  type CreateAdminUserResult,
} from "@/lib/api/admin";
import {
  ACCESS_TYPE_LABELS,
  DURATION_OPTIONS,
  generateSecurePassword,
} from "@/components/admin/adminUserUtils";

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: (result: CreateAdminUserResult) => void;
};

const inputClass =
  "w-full rounded border border-cyan-500/40 bg-black/70 px-3 py-2 text-sm text-cyan-50 outline-none focus:border-cyan-400";

export function AdminCreateUserModal({ open, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [accessType, setAccessType] =
    useState<CreateAdminUserPayload["access_type"]>("beta");
  const [plan, setPlan] =
    useState<CreateAdminUserPayload["plan"]>("elite_founding");
  const [duration, setDuration] = useState<number | "indefinite">(30);
  const [minutesDaily, setMinutesDaily] = useState(120);
  const [initialBalance, setInitialBalance] = useState("0");
  const [passwordMode, setPasswordMode] = useState<"auto" | "manual">("manual");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [adminNotes, setAdminNotes] = useState("");
  const [sendWelcome, setSendWelcome] = useState(true);
  const [forceChange, setForceChange] = useState(true);
  const [notifyLogin, setNotifyLogin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetForm = useCallback(() => {
    setName("");
    setEmail("");
    setPhone("");
    setAccessType("beta");
    setPlan("elite_founding");
    setDuration(30);
    setMinutesDaily(120);
    setInitialBalance("0");
    setPasswordMode("manual");
    setPassword("");
    setAdminNotes("");
    setSendWelcome(true);
    setForceChange(true);
    setNotifyLogin(false);
    setError(null);
  }, []);

  useEffect(() => {
    if (!open) return;
    resetForm();
  }, [open, resetForm]);

  useEffect(() => {
    if (passwordMode === "auto" && !password) {
      setPassword(generateSecurePassword());
    }
  }, [passwordMode, password]);

  if (!open) return null;

  const handleSubmit = async () => {
    setError(null);
    const pwd =
      passwordMode === "auto" ? password || generateSecurePassword() : password;
    if (pwd.length < 8) {
      setError("Contraseña mínimo 8 caracteres.");
      return;
    }
    const balance = parseFloat(initialBalance) || 0;
    setBusy(true);
    try {
      const payload: CreateAdminUserPayload = {
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        access_type: accessType,
        plan,
        duration_days: duration,
        minutes_daily: minutesDaily,
        initial_balance: balance,
        password: pwd,
        send_welcome_email: sendWelcome,
        force_password_change: forceChange,
        notify_on_first_login: notifyLogin,
        admin_notes: adminNotes.trim() || undefined,
      };
      const result = await createAdminUser(payload);
      onCreated(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al crear usuario");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-create-user-title"
    >
      <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-lg border border-cyan-500/50 bg-[#0a0f14] p-5 shadow-[0_0_40px_rgba(0,229,255,0.15)]">
        <h2
          id="admin-create-user-title"
          className="font-[family-name:var(--font-orbitron)] text-base font-bold tracking-wider text-cyan-300"
        >
          ➕ AGREGAR NUEVO USUARIO
        </h2>
        <p className="ced-hud-text-muted mt-1 text-xs">
          Acceso manual sin Stripe — Zelle, beta, regalo o founding.
        </p>

        <div className="mt-4 space-y-3">
          <label className="block text-xs text-cyan-400/90">
            Nombre completo *
            <input
              className={`${inputClass} mt-1`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          </label>
          <label className="block text-xs text-cyan-400/90">
            Email *
            <input
              type="email"
              className={`${inputClass} mt-1`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="block text-xs text-cyan-400/90">
            Teléfono (opcional)
            <input
              className={`${inputClass} mt-1`}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>

          <fieldset className="space-y-1">
            <legend className="text-xs text-cyan-400/90">Tipo de acceso *</legend>
            {(
              [
                ["paid", "Cliente PAGO"],
                ["beta", "Beta tester GRATIS"],
                ["founding_gift", "Founding Member REGALO"],
                ["coadmin", "Co-admin"],
              ] as const
            ).map(([val, label]) => (
              <label key={val} className="flex items-center gap-2 text-sm text-cyan-100">
                <input
                  type="radio"
                  name="access_type"
                  checked={accessType === val}
                  onChange={() => setAccessType(val)}
                />
                {label}
              </label>
            ))}
          </fieldset>

          <label className="block text-xs text-cyan-400/90">
            Plan asignado *
            <select
              className={`${inputClass} mt-1`}
              value={plan}
              onChange={(e) =>
                setPlan(e.target.value as CreateAdminUserPayload["plan"])
              }
            >
              <option value="elite_founding">ELITE FOUNDING</option>
              <option value="elite_regular">ELITE REGULAR</option>
            </select>
          </label>

          <label className="block text-xs text-cyan-400/90">
            Duración del acceso
            <select
              className={`${inputClass} mt-1`}
              value={String(duration)}
              onChange={(e) => {
                const v = e.target.value;
                setDuration(v === "indefinite" ? "indefinite" : Number(v));
              }}
            >
              {DURATION_OPTIONS.map((o) => (
                <option key={String(o.value)} value={String(o.value)}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs text-cyan-400/90">
            Minutos diarios
            <select
              className={`${inputClass} mt-1`}
              value={minutesDaily}
              onChange={(e) => setMinutesDaily(Number(e.target.value))}
            >
              {[60, 90, 120, 180, 240].map((m) => (
                <option key={m} value={m}>
                  {m} min
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs text-cyan-400/90">
            Saldo inicial extra ($)
            <input
              type="number"
              min={0}
              step={0.01}
              className={`${inputClass} mt-1`}
              value={initialBalance}
              onChange={(e) => setInitialBalance(e.target.value)}
            />
          </label>

          <fieldset className="space-y-1">
            <legend className="text-xs text-cyan-400/90">Contraseña</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                checked={passwordMode === "auto"}
                onChange={() => {
                  setPasswordMode("auto");
                  setPassword(generateSecurePassword());
                }}
              />
              Generar automática
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                checked={passwordMode === "manual"}
                onChange={() => setPasswordMode("manual")}
              />
              Yo especifico
            </label>
          </fieldset>

          <label className="block text-xs text-cyan-400/90">
            Contraseña inicial *
            <div className="mt-1 flex gap-2">
              <input
                type={showPassword ? "text" : "password"}
                className={inputClass}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
              <button
                type="button"
                className="shrink-0 rounded border border-cyan-600/60 px-2 text-[10px] text-cyan-400"
                onClick={() => setPassword(generateSecurePassword())}
              >
                🎲
              </button>
            </div>
            <label className="mt-1 flex items-center gap-2 text-xs text-cyan-300/80">
              <input
                type="checkbox"
                checked={showPassword}
                onChange={(e) => setShowPassword(e.target.checked)}
              />
              Mostrar contraseña
            </label>
          </label>

          <label className="block text-xs text-cyan-400/90">
            Notas internas
            <textarea
              className={`${inputClass} mt-1 min-h-[60px]`}
              value={adminNotes}
              onChange={(e) => setAdminNotes(e.target.value)}
            />
          </label>

          <label className="flex items-center gap-2 text-xs text-cyan-200">
            <input
              type="checkbox"
              checked={sendWelcome}
              onChange={(e) => setSendWelcome(e.target.checked)}
            />
            Enviar email de bienvenida
          </label>
          <label className="flex items-center gap-2 text-xs text-cyan-200">
            <input
              type="checkbox"
              checked={forceChange}
              onChange={(e) => setForceChange(e.target.checked)}
            />
            Pedir cambio de contraseña al primer login
          </label>
          <label className="flex items-center gap-2 text-xs text-cyan-200/60">
            <input
              type="checkbox"
              checked={notifyLogin}
              onChange={(e) => setNotifyLogin(e.target.checked)}
              disabled
            />
            Notificarme cuando se conecte (próximamente)
          </label>
        </div>

        {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <CedButton variant="ghost" type="button" onClick={onClose} disabled={busy}>
            Cancelar
          </CedButton>
          <CedButton type="button" disabled={busy} onClick={() => void handleSubmit()}>
            {busy ? "CREANDO…" : "✅ CREAR USUARIO"}
          </CedButton>
        </div>
      </div>
    </div>
  );
}
