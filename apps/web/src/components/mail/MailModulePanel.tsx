"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { CedButton } from "@ced/ui";

import { parseApiJson } from "@/lib/api/http";
import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

type MailMessage = {
  id: string;
  from_name?: string;
  from?: string;
  subject?: string;
  relative_date?: string;
  snippet?: string;
};

const GMAIL_NOTE: Record<string, string> = {
  connected: "Correo conectado. CED ya puede leerlo y responder cuando usted confirme.",
  error: "No se pudo conectar el correo. Inténtelo de nuevo.",
  scope_read: "Falta permiso para leer. Vuelva a conectar y acéptelo.",
  scope_send: "Falta permiso para enviar. Vuelva a conectar y acepte el envío.",
};

export function MailModulePanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await proxyFetchAuthed("google/gmail/inbox");
      const data = await parseApiJson<{
        connected?: boolean;
        messages?: MailMessage[];
        detail?: string;
      }>(res);
      if (!res.ok) {
        setError(data.detail || "No se pudo leer el correo.");
        setConnected(false);
        setMessages([]);
        return;
      }
      setConnected(Boolean(data.connected));
      setMessages(Array.isArray(data.messages) ? data.messages : []);
    } catch {
      setError("No se pudo leer el correo.");
      setConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const flag = searchParams.get("gmail");
    if (flag) {
      setNote(GMAIL_NOTE[flag] ?? `Resultado: ${flag}`);
      router.replace("/dashboard/correo", { scroll: false });
    }
    void load();
  }, [load, router, searchParams]);

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const res = await proxyFetchAuthed("google/gmail/oauth-url");
      const data = await parseApiJson<{ url?: string; detail?: string }>(res);
      if (!res.ok || !data.url) {
        setError(data.detail || "No se pudo abrir la conexión de Gmail.");
        return;
      }
      window.location.href = data.url;
    } catch {
      setError("No se pudo conectar el correo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[#05080f] text-cyan-50">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />
      <header className="flex shrink-0 flex-wrap items-end justify-between gap-4 border-b border-cyan-500/20 px-4 py-5 sm:px-8">
        <div>
          <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.38em] text-cyan-400">
            SISTEMA · CORREO
          </p>
          <h1 className="mt-1 font-[family-name:var(--font-orbitron)] text-2xl text-cyan-50 sm:text-4xl">
            Correo
          </h1>
          <p className="mt-2 max-w-2xl font-sans text-sm tracking-normal text-cyan-200/80">
            CED lee la bandeja y prepara la respuesta. El envío sale solo cuando usted dice que sí.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={[
              "rounded-full border px-3 py-1 text-xs",
              connected
                ? "border-cyan-400/60 bg-cyan-400/15 text-cyan-100"
                : "border-white/15 text-cyan-300/70",
            ].join(" ")}
          >
            {connected ? "Conectado" : "Sin conectar"}
          </span>
          <CedButton type="button" disabled={busy} onClick={() => void connect()}>
            {busy ? "Conectando…" : connected ? "Reconectar" : "Conectar Gmail"}
          </CedButton>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 overflow-y-auto px-4 py-6 sm:px-8">
        {note ? (
          <p className="rounded-lg border border-cyan-400/40 bg-cyan-950/40 px-3 py-2 font-sans text-sm tracking-normal text-cyan-100">
            {note}
          </p>
        ) : null}
        {error ? (
          <p className="rounded-lg border border-red-400/40 bg-red-950/40 px-3 py-2 font-sans text-sm tracking-normal text-red-100">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="font-sans text-sm text-cyan-200/70">Leyendo bandeja…</p>
        ) : null}

        {!loading && !connected ? (
          <p className="font-sans text-sm tracking-normal text-cyan-200/80">
            Pulse Conectar Gmail y acepte leer y enviar. Después puede pedirle a CED: «léeme los correos» o «respóndele a este».
          </p>
        ) : null}

        {!loading && connected && messages.length === 0 ? (
          <p className="font-sans text-sm tracking-normal text-cyan-200/80">
            La bandeja no tiene correos recientes.
          </p>
        ) : null}

        <ul className="flex flex-col gap-2">
          {messages.map((msg) => (
            <li
              key={msg.id}
              className="rounded-lg border border-cyan-500/20 bg-cyan-950/20 px-4 py-3"
            >
              <div className="flex items-baseline justify-between gap-3">
                <p className="truncate font-sans text-sm text-cyan-50">
                  {msg.from_name || msg.from || "Sin remitente"}
                </p>
                <p className="shrink-0 font-sans text-xs text-cyan-300/70">
                  {msg.relative_date || ""}
                </p>
              </div>
              <p className="mt-1 truncate font-sans text-sm text-cyan-100">
                {msg.subject || "(sin asunto)"}
              </p>
              {msg.snippet ? (
                <p className="mt-1 line-clamp-2 font-sans text-xs tracking-normal text-cyan-200/70">
                  {msg.snippet}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
