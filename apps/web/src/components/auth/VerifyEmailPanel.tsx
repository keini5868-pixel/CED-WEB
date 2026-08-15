"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { CedButton } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { LOGIN_PATH, sanitizeAuthNext } from "@/lib/auth/paths";
import { apiUrl, isSupabaseConfigured } from "@/lib/env";

export function VerifyEmailPanel() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") || "";
  const next = sanitizeAuthNext(searchParams.get("next"));
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function resend() {
    if (!email || !isSupabaseConfigured()) {
      setError("Indica un email válido o configura Supabase.");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const res = await fetch(`${apiUrl()}/v1/auth/resend-verification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), next }),
      });
      let data: { detail?: string; message?: string } | null = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }
      if (!res.ok) {
        setError(
          (typeof data?.detail === "string" && data.detail) ||
            "No se pudo reenviar el correo. Intenta de nuevo.",
        );
        return;
      }
      setMessage(data?.message || "Email de verificación reenviado.");
    } catch {
      setError("No se pudo conectar con el servidor.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthCard title="VERIFICA TU EMAIL" subtitle="15 min de voz al hablar · 7 días de imágenes">
      <p className="text-center text-sm text-cyan-400/90">
        Enviamos un enlace a{" "}
        <span className="font-semibold text-cyan-300">
          {email || "tu correo"}
        </span>
        . Haz clic para activar la cuenta.
      </p>
      {message ? <p className="mt-4 text-center text-xs text-cyan-400">{message}</p> : null}
      {error ? <p className="mt-4 text-center text-xs text-red-400">{error}</p> : null}
      <CedButton
        type="button"
        variant="secondary"
        fullWidth
        className="mt-6"
        disabled={loading || !email}
        onClick={resend}
      >
        {loading ? "…" : "REENVIAR EMAIL"}
      </CedButton>
      <Link
        href={`${LOGIN_PATH}?next=${encodeURIComponent(next)}`}
        className="mt-6 block text-center text-xs text-cyan-500 hover:text-cyan-300"
      >
        Ya verifiqué — Iniciar sesión
      </Link>
    </AuthCard>
  );
}
