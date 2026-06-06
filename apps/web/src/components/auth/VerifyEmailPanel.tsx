"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { CedButton } from "@ced/ui";
import { AuthCard } from "@/components/auth/AuthCard";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

export function VerifyEmailPanel() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") || "";
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
    const supabase = createClient();
    const { error: authError } = await supabase.auth.resend({
      type: "signup",
      email: email.trim(),
    });
    setLoading(false);
    if (authError) {
      setError(authError.message);
      return;
    }
    setMessage("Email de verificación reenviado.");
  }

  return (
    <AuthCard title="VERIFICA TU EMAIL" subtitle="7 días gratis te esperan">
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
        href="/login"
        className="mt-6 block text-center text-xs text-cyan-500 hover:text-cyan-300"
      >
        Ya verifiqué — Iniciar sesión
      </Link>
    </AuthCard>
  );
}
