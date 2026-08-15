"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { CedButton, CedInput } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthDivider, GoogleAuthButton } from "@/components/auth/GoogleAuthButton";
import { LOGIN_PATH, sanitizeAuthNext } from "@/lib/auth/paths";
import { apiUrl, isGoogleAuthEnabled, isSupabaseConfigured } from "@/lib/env";

function registerErrorMessage(status: number, detail: unknown): string {
  const text =
    typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : "";
  if (text) return text;
  if (status === 503) {
    return "El servicio de correo no está disponible. Intenta más tarde o contacta soporte.";
  }
  if (status === 409) {
    return "Ya existe una cuenta con este correo. Inicia sesión o usa otro correo.";
  }
  return "No se pudo crear la cuenta. Intenta de nuevo.";
}

function resolvePmOffer(
  offerParam: string,
  nextPath: string,
): "cierre" | "" {
  const direct = offerParam.trim().toLowerCase();
  if (direct === "cierre" || direct === "fitline") return "cierre";
  try {
    const fromNext =
      new URL(nextPath, "https://ced.local").searchParams.get("offer")?.toLowerCase() ||
      "";
    if (fromNext === "cierre" || fromNext === "fitline") return "cierre";
  } catch {
    /* ignore */
  }
  return "";
}

export function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = sanitizeAuthNext(searchParams.get("next"));
  const offer = resolvePmOffer(searchParams.get("offer") || "", next);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const configured = isSupabaseConfigured();
  const googleNext =
    offer && !next.includes("offer=")
      ? `${next}${next.includes("?") ? "&" : "?"}offer=${offer}`
      : next;
  const loginHref = `${LOGIN_PATH}?next=${encodeURIComponent(googleNext)}`;

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!configured) {
      setError("Supabase no configurado.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Registro manual vía API CED + Resend (evita el SMTP roto de Supabase Auth).
      // Google OAuth NO pasa por aquí — sigue en GoogleAuthButton sin cambios.
      const res = await fetch(`${apiUrl()}/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          next: googleNext,
          ...(offer ? { offer } : {}),
        }),
      });
      let data: unknown = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }
      if (!res.ok) {
        const detail =
          data && typeof data === "object" && "detail" in data
            ? (data as { detail: unknown }).detail
            : data;
        setError(registerErrorMessage(res.status, detail));
        return;
      }
      router.push(
        `/verify-email?email=${encodeURIComponent(email.trim())}&next=${encodeURIComponent(googleNext)}`,
      );
    } catch {
      setError("No se pudo conectar con el servidor. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  const payingFlow = next.startsWith("/pricing");
  const pmOfferFlow = offer === "cierre";

  return (
    <AuthCard
      title="REGISTRO"
      subtitle={
        payingFlow
          ? "Crea tu cuenta y continúa al pago"
          : pmOfferFlow
            ? "Prueba FitLine · 15 min de voz al hablar"
            : "15 min de voz al hablar · 7 días de imágenes"
      }
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
      {pmOfferFlow && !payingFlow ? (
        <p className="mb-4 rounded border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs text-emerald-200">
          Al verificar tu correo activas CED PM International: 15 minutos de voz
          Jarvis con conocimiento FitLine. El reloj de 24 h arranca cuando
          empieces a hablar (si no usas la voz, no vence). Imágenes y PDF
          durante 7 días. Luego puedes suscribirte a $22/mes o recargar desde $10.
        </p>
      ) : !payingFlow ? (
        <p className="mb-4 rounded border border-cyan-500/30 bg-cyan-500/5 p-3 text-xs text-cyan-200">
          Al verificar tu correo tienes 15 minutos de voz: el reloj de 24 h
          arranca cuando empieces a hablar (si no usas la voz, no vence).
          Imágenes y PDF durante 7 días. El chat de texto sigue disponible.
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
          {loading
            ? "CREANDO…"
            : payingFlow
              ? "CREAR CUENTA Y PAGAR"
              : "CREAR CUENTA"}
        </CedButton>
      </form>
      {isGoogleAuthEnabled() ? (
        <>
          <AuthDivider />
          <GoogleAuthButton
            label="Registrarse con Google"
            next={googleNext}
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
