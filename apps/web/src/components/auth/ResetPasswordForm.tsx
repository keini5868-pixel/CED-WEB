"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CedButton, CedInput } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { DASHBOARD_PATH } from "@/lib/auth/paths";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = searchParams.get("code");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured() || !code) {
      setReady(!code);
      return;
    }
    const supabase = createClient();
    supabase.auth.exchangeCodeForSession(code).then(({ error: authError }) => {
      if (authError) {
        setError(authError.message);
        setReady(false);
        return;
      }
      setReady(true);
    });
  }, [code]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError("Mínimo 8 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setLoading(true);
    setError(null);
    const supabase = createClient();
    const { error: authError } = await supabase.auth.updateUser({ password });
    setLoading(false);
    if (authError) {
      setError(authError.message);
      return;
    }
    router.push(DASHBOARD_PATH);
    router.refresh();
  }

  if (!code) {
    return (
      <AuthCard title="ENLACE INVÁLIDO" subtitle="Solicita uno nuevo">
        <p className="text-center text-xs text-cyan-600">
          Abre el enlace desde el email de recuperación o pide otro en{" "}
          <Link href="/forgot-password" className="text-cyan-400 underline">
            recuperar contraseña
          </Link>
          .
        </p>
      </AuthCard>
    );
  }

  if (!ready && !error) {
    return (
      <AuthCard title="VERIFICANDO" subtitle="Un momento…">
        <p className="text-center text-xs text-cyan-600">Validando enlace…</p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="NUEVA CONTRASEÑA" subtitle="CED Élite">
      <form onSubmit={handleSubmit} className="space-y-4">
        <CedInput
          label="Contraseña nueva"
          type="password"
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
        <CedInput
          label="Confirmar"
          type="password"
          name="confirm"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
          minLength={8}
        />
        {error ? <p className="text-xs text-red-400">{error}</p> : null}
        <CedButton type="submit" fullWidth disabled={loading || !ready}>
          {loading ? "GUARDANDO…" : "ACTUALIZAR"}
        </CedButton>
      </form>
    </AuthCard>
  );
}
