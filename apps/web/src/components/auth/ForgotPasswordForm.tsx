"use client";

import Link from "next/link";
import { useState } from "react";

import { CedButton, CedInput } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { RESET_PASSWORD_PATH } from "@/lib/auth/paths";
import { createClient } from "@/lib/supabase/client";
import { appUrl, isSupabaseConfigured } from "@/lib/env";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isSupabaseConfigured()) {
      setError("Supabase no configurado.");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);
    const supabase = createClient();
    const { error: authError } = await supabase.auth.resetPasswordForEmail(
      email.trim(),
      {
        redirectTo: `${appUrl()}${RESET_PASSWORD_PATH}`,
      },
    );
    setLoading(false);
    if (authError) {
      setError(authError.message);
      return;
    }
    setMessage(
      "Si el email existe, recibirás un enlace para restablecer tu contraseña.",
    );
  }

  return (
    <AuthCard title="RECUPERAR" subtitle="Te enviaremos un enlace seguro">
      <form onSubmit={handleSubmit} className="space-y-4">
        <CedInput
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        {error ? <p className="text-xs text-red-400">{error}</p> : null}
        {message ? <p className="text-xs text-cyan-400">{message}</p> : null}
        <CedButton type="submit" fullWidth disabled={loading}>
          {loading ? "ENVIANDO…" : "ENVIAR ENLACE"}
        </CedButton>
      </form>
      <Link
        href="/login"
        className="mt-6 block text-center text-xs text-cyan-500 hover:text-cyan-300"
      >
        ← Volver al login
      </Link>
    </AuthCard>
  );
}
