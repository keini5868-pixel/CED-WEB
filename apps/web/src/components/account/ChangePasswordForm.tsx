"use client";

import { useEffect, useState } from "react";

import { CedButton, CedInput } from "@ced/ui";

import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

function hasEmailPasswordIdentity(
  identities: { provider?: string }[] | undefined,
): boolean {
  return (identities ?? []).some((i) => i.provider === "email");
}

/**
 * Logged-in password change — verifies the current password via
 * signInWithPassword, then updateUser. No recovery email required.
 */
export function ChangePasswordForm() {
  const [email, setEmail] = useState<string | null>(null);
  const [hasPassword, setHasPassword] = useState(true);
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      setReady(true);
      return;
    }
    const supabase = createClient();
    void supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null);
      setHasPassword(hasEmailPasswordIdentity(data.user?.identities));
      setReady(true);
    });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isSupabaseConfigured()) {
      setError("Supabase no configurado.");
      return;
    }
    if (password.length < 8) {
      setError("La nueva contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("Las contraseñas nuevas no coinciden.");
      return;
    }
    if (hasPassword && !currentPassword) {
      setError("Escribe tu contraseña actual.");
      return;
    }
    if (hasPassword && currentPassword === password) {
      setError("La nueva contraseña debe ser distinta a la actual.");
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);
    const supabase = createClient();

    if (hasPassword) {
      if (!email) {
        setLoading(false);
        setError("No hay email en la sesión. Vuelve a iniciar sesión.");
        return;
      }
      const { error: verifyError } = await supabase.auth.signInWithPassword({
        email,
        password: currentPassword,
      });
      if (verifyError) {
        setLoading(false);
        setError("La contraseña actual no es correcta.");
        return;
      }
    }

    const { error: updateError } = await supabase.auth.updateUser({ password });
    setLoading(false);
    if (updateError) {
      setError(updateError.message);
      return;
    }

    setCurrentPassword("");
    setPassword("");
    setConfirm("");
    setHasPassword(true);
    setMessage(
      hasPassword
        ? "Contraseña actualizada. Ya puedes usarla en el próximo inicio de sesión."
        : "Contraseña creada. También puedes entrar con email y esta contraseña.",
    );
  }

  if (!ready) {
    return (
      <p className="text-xs text-cyan-100/60">Cargando cuenta…</p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {email ? (
        <p className="text-xs text-cyan-100/60">
          Cuenta: <span className="text-cyan-200">{email}</span>
        </p>
      ) : null}

      {!hasPassword ? (
        <p className="rounded border border-amber-500/30 bg-amber-950/20 px-3 py-2 text-xs text-amber-100/90">
          Esta cuenta entró con Google y aún no tiene contraseña de email.
          Puedes crear una aquí para también iniciar sesión con email.
        </p>
      ) : null}

      {hasPassword ? (
        <CedInput
          label="Contraseña actual"
          type="password"
          name="currentPassword"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
        />
      ) : null}

      <CedInput
        label={hasPassword ? "Contraseña nueva" : "Crear contraseña"}
        type="password"
        name="newPassword"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={8}
      />
      <CedInput
        label="Confirmar contraseña nueva"
        type="password"
        name="confirmPassword"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        required
        minLength={8}
      />

      {error ? <p className="text-xs text-red-400">{error}</p> : null}
      {message ? <p className="text-xs text-cyan-400">{message}</p> : null}

      <CedButton type="submit" disabled={loading}>
        {loading
          ? "GUARDANDO…"
          : hasPassword
            ? "CAMBIAR CONTRASEÑA"
            : "CREAR CONTRASEÑA"}
      </CedButton>
    </form>
  );
}
