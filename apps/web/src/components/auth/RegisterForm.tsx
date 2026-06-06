"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CedButton, CedInput } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { DASHBOARD_PATH } from "@/lib/auth/paths";
import { createClient } from "@/lib/supabase/client";
import { appUrl, isSupabaseConfigured } from "@/lib/env";

export function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const configured = isSupabaseConfigured();

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!configured) {
      setError("Supabase no configurado.");
      return;
    }
    setLoading(true);
    setError(null);
    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        data: { full_name: fullName.trim() },
        emailRedirectTo: `${appUrl()}/auth/callback?next=${encodeURIComponent(DASHBOARD_PATH)}`,
      },
    });
    setLoading(false);
    if (authError) {
      setError(authError.message);
      return;
    }
    if (data.user && !data.session) {
      router.push(`/verify-email?email=${encodeURIComponent(email.trim())}`);
      return;
    }
    router.push(DASHBOARD_PATH);
    router.refresh();
  }

  async function handleGoogle() {
    if (!configured) {
      setError("Supabase no configurado.");
      return;
    }
    setLoading(true);
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${appUrl()}/auth/callback?next=${encodeURIComponent(DASHBOARD_PATH)}`,
      },
    });
  }

  return (
    <AuthCard title="REGISTRO" subtitle="7 días gratis · sin tarjeta">
      {!configured ? (
        <p className="mb-4 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
          Esperando credenciales Supabase en <code>.env.local</code>
        </p>
      ) : null}
      <form onSubmit={handleRegister} className="space-y-4">
        <CedInput
          label="Nombre"
          name="name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <CedInput
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <CedInput
          label="Contraseña"
          type="password"
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
        {error ? <p className="text-xs text-red-400">{error}</p> : null}
        <CedButton type="submit" fullWidth disabled={loading}>
          {loading ? "CREANDO…" : "CREAR CUENTA"}
        </CedButton>
      </form>
      <CedButton
        type="button"
        variant="secondary"
        fullWidth
        className="mt-4"
        disabled={loading}
        onClick={handleGoogle}
      >
        REGISTRO CON GOOGLE
      </CedButton>
      <p className="mt-6 text-center text-xs text-cyan-600">
        ¿Ya tienes cuenta?{" "}
        <Link href="/login" className="text-cyan-400 hover:underline">
          Iniciar sesión
        </Link>
      </p>
      <Link
        href="/"
        className="mt-4 block text-center text-xs text-cyan-700 hover:text-cyan-500"
      >
        ← Inicio
      </Link>
    </AuthCard>
  );
}
