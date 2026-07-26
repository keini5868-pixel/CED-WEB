"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CedButton, CedInput } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthDivider, GoogleAuthButton } from "@/components/auth/GoogleAuthButton";
import { SIGNUP_PATH, sanitizeAuthNext } from "@/lib/auth/paths";
import { createClient } from "@/lib/supabase/client";
import { isGoogleAuthEnabled, isSupabaseConfigured } from "@/lib/env";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = sanitizeAuthNext(searchParams.get("next"));
  const urlError = searchParams.get("error");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const configured = isSupabaseConfigured();

  useEffect(() => {
    if (urlError === "auth_callback") {
      setError("No se pudo completar la autenticación. Intenta de nuevo.");
    }
  }, [urlError]);

  async function handleEmailLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!configured) {
      setError("Supabase no configurado. Añade credenciales en .env.local");
      return;
    }
    setLoading(true);
    setError(null);
    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    setLoading(false);
    if (authError) {
      if (authError.message.toLowerCase().includes("email not confirmed")) {
        setError("Confirma tu email antes de entrar.");
        router.push(
          `/verify-email?email=${encodeURIComponent(email.trim())}&next=${encodeURIComponent(next)}`,
        );
        return;
      }
      const msg = authError.message || "";
      if (
        msg.toLowerCase().includes("invalid login credentials") ||
        msg.toLowerCase().includes("invalid_credentials")
      ) {
        setError(
          "Credenciales incorrectas. Si te registraste con Google, usa el botón de Google. Si olvidaste la contraseña, restablécela abajo.",
        );
        return;
      }
      setError(msg);
      return;
    }
    if (data.user && !data.user.email_confirmed_at) {
      router.push(
        `/verify-email?email=${encodeURIComponent(email.trim())}&next=${encodeURIComponent(next)}`,
      );
      return;
    }
    router.push(next);
    router.refresh();
  }

  return (
    <AuthCard title="AUTENTICACIÓN" subtitle="Acceso CED Élite">
      {!configured ? (
        <p className="mb-4 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
          Configura <code className="text-cyan-400">.env.local</code> con Supabase.
        </p>
      ) : null}
      <form onSubmit={handleEmailLogin} className="space-y-4">
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
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <div className="text-right">
          <Link
            href="/forgot-password"
            className="text-[10px] text-cyan-500 hover:text-cyan-300"
          >
            ¿Olvidaste tu contraseña?
          </Link>
        </div>
        {error ? <p className="text-xs text-red-400">{error}</p> : null}
        <CedButton type="submit" fullWidth disabled={loading}>
          {loading ? "CONECTANDO…" : "ENTRAR"}
        </CedButton>
      </form>
      {isGoogleAuthEnabled() ? (
        <>
          <AuthDivider />
          <GoogleAuthButton
            label="Iniciar sesión con Google"
            next={next}
            disabled={loading || !configured}
            onError={setError}
          />
        </>
      ) : null}
      <p className="mt-6 text-center text-xs text-cyan-600">
        ¿Sin cuenta?{" "}
        <Link
          href={`${SIGNUP_PATH}?next=${encodeURIComponent(next)}`}
          className="text-cyan-400 hover:underline"
        >
          {next.startsWith("/pricing") ? "Crear cuenta y pagar" : "Registro — 7 días gratis"}
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
