"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { CedButton, CedInput } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthDivider, GoogleAuthButton } from "@/components/auth/GoogleAuthButton";
import { LOGIN_PATH, sanitizeAuthNext } from "@/lib/auth/paths";
import { createClient } from "@/lib/supabase/client";
import { appUrl, isGoogleAuthEnabled, isSupabaseConfigured } from "@/lib/env";

export function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = sanitizeAuthNext(searchParams.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const configured = isSupabaseConfigured();
  const loginHref = `${LOGIN_PATH}?next=${encodeURIComponent(next)}`;
  const callbackNext = encodeURIComponent(next);

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
        emailRedirectTo: `${appUrl()}/auth/callback?next=${callbackNext}`,
      },
    });
    setLoading(false);
    if (authError) {
      setError(authError.message);
      return;
    }
    // Supabase no devuelve error si el correo ya existe y está confirmado
    // (anti-enumeración): responde un usuario "obfuscado" con `identities`
    // vacío y sin sesión — idéntico en apariencia a un registro nuevo
    // pendiente de confirmar. Sin esta comprobación, quien reutiliza un
    // correo de una cuenta vieja (p. ej. una ya degradada a plan Básico
    // gratis tras un trial expirado) termina en "revisa tu correo" sin
    // enterarse de que en realidad sigue en su cuenta antigua — nunca
    // obtiene el trial nuevo de 5 min/día de voz que sí le corresponde a
    // una cuenta realmente nueva.
    if (data.user && data.user.identities?.length === 0) {
      setError(
        "Ya existe una cuenta con este correo. Inicia sesión en su lugar, o usa otro correo para crear una cuenta nueva.",
      );
      return;
    }
    if (data.user && !data.session) {
      router.push(
        `/verify-email?email=${encodeURIComponent(email.trim())}&next=${callbackNext}`,
      );
      return;
    }
    router.push(next);
    router.refresh();
  }

  const payingFlow = next.startsWith("/pricing");

  return (
    <AuthCard
      title="REGISTRO"
      subtitle={payingFlow ? "Crea tu cuenta y continúa al pago" : "7 días gratis · sin tarjeta"}
    >
      {!configured ? (
        <p className="mb-4 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
          Esperando credenciales Supabase en <code>.env.local</code>
        </p>
      ) : null}
      {payingFlow ? (
        <p className="mb-4 rounded border border-cyan-500/30 bg-cyan-500/5 p-3 text-xs text-cyan-300">
          Después de crear la cuenta te llevamos a Stripe para registrar tu tarjeta.
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
          {loading ? "CREANDO…" : payingFlow ? "CREAR CUENTA Y PAGAR" : "CREAR CUENTA"}
        </CedButton>
      </form>
      {isGoogleAuthEnabled() ? (
        <>
          <AuthDivider />
          <GoogleAuthButton
            label="Registrarse con Google"
            next={next}
            disabled={loading || !configured}
            onError={setError}
          />
        </>
      ) : null}
      <p className="mt-6 text-center text-xs text-cyan-600">
        ¿Ya tienes cuenta?{" "}
        <Link href={loginHref} className="text-cyan-400 hover:underline">
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
