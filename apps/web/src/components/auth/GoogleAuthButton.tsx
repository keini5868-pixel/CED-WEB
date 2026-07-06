"use client";

import { useState } from "react";

import { signInWithGoogle } from "@/lib/auth/google-oauth";

type GoogleAuthButtonProps = {
  label: string;
  next?: string | null;
  disabled?: boolean;
  onError?: (message: string) => void;
};

function GoogleLogo() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

export function AuthDivider() {
  return (
    <div className="my-4 flex items-center gap-3 text-xs text-cyan-500/40">
      <div className="h-px flex-1 bg-cyan-400/20" />
      <span>O</span>
      <div className="h-px flex-1 bg-cyan-400/20" />
    </div>
  );
}

export function GoogleAuthButton({
  label,
  next,
  disabled = false,
  onError,
}: GoogleAuthButtonProps) {
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    setBusy(true);
    const result = await signInWithGoogle(next);
    if (result.error) {
      onError?.(result.error);
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      disabled={disabled || busy}
      onClick={() => void handleClick()}
      className="flex w-full cursor-pointer items-center justify-center gap-3 rounded-lg border border-cyan-400/30 bg-white/5 px-6 py-3 text-sm text-cyan-300 transition hover:border-cyan-400/50 hover:bg-cyan-400/10 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <GoogleLogo />
      {busy ? "Redirigiendo…" : label}
    </button>
  );
}
