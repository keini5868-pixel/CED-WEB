"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { CedButton } from "@ced/ui";

import {
  fetchGoogleCalendarOAuthUrl,
  fetchGoogleCalendarStatus,
  fetchGoogleGmailOAuthUrl,
  fetchGoogleGmailStatus,
} from "@/lib/api/google";

export const GOOGLE_CALENDAR_CONNECTED_EVENT = "ced:google-calendar-connected";
export const GOOGLE_GMAIL_CONNECTED_EVENT = "ced:google-gmail-connected";

const CALENDAR_TOAST: Record<string, string> = {
  connected: "Google Calendar conectado correctamente.",
  error: "No se pudo conectar Google Calendar.",
  token_failed: "Google no devolvió token para Calendar.",
  missing_config: "OAuth Calendar no configurado en el servidor.",
};

const GMAIL_TOAST: Record<string, string> = {
  connected: "Gmail conectado correctamente.",
  error: "No se pudo conectar Gmail.",
  token_failed: "Google no devolvió token para Gmail.",
  missing_config: "OAuth Gmail no configurado en el servidor.",
};

export function GoogleOAuthCallbackBanner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const calendar = searchParams.get("google_calendar");
    const gmail = searchParams.get("google_gmail");
    if (calendar) {
      setMessage(CALENDAR_TOAST[calendar] ?? `Calendar: ${calendar}`);
      if (calendar === "connected") {
        window.dispatchEvent(new Event(GOOGLE_CALENDAR_CONNECTED_EVENT));
      }
      router.replace("/dashboard", { scroll: false });
      return;
    }
    if (gmail) {
      setMessage(GMAIL_TOAST[gmail] ?? `Gmail: ${gmail}`);
      if (gmail === "connected") {
        window.dispatchEvent(new Event(GOOGLE_GMAIL_CONNECTED_EVENT));
      }
      router.replace("/dashboard", { scroll: false });
    }
  }, [searchParams, router]);

  if (!message) return null;

  const ok = message.includes("correctamente");
  return (
    <div
      className={[
        "mx-auto mb-3 max-w-2xl rounded border px-4 py-2 text-center text-sm",
        ok
          ? "border-emerald-500/50 bg-emerald-950/40 text-emerald-200"
          : "border-red-500/50 bg-red-950/40 text-red-200",
      ].join(" ")}
      role="status"
    >
      {message}
    </div>
  );
}

export function ConnectGoogleServicesPanel() {
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [busy, setBusy] = useState<"calendar" | "gmail" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [cal, mail] = await Promise.all([
      fetchGoogleCalendarStatus(),
      fetchGoogleGmailStatus(),
    ]);
    if (cal) setCalendarConnected(Boolean(cal.connected));
    if (mail) setGmailConnected(Boolean(mail.connected));
  }, []);

  useEffect(() => {
    void refresh();
    const onCal = () => void refresh();
    const onMail = () => void refresh();
    window.addEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onCal);
    window.addEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onMail);
    return () => {
      window.removeEventListener(GOOGLE_CALENDAR_CONNECTED_EVENT, onCal);
      window.removeEventListener(GOOGLE_GMAIL_CONNECTED_EVENT, onMail);
    };
  }, [refresh]);

  const connectCalendar = async () => {
    setBusy("calendar");
    setError(null);
    try {
      const { url, error: oauthError } = await fetchGoogleCalendarOAuthUrl();
      if (!url) {
        setError(oauthError || "No se pudo iniciar OAuth Calendar.");
        return;
      }
      window.location.href = url;
    } catch {
      setError("Error al conectar Google Calendar.");
    } finally {
      setBusy(null);
    }
  };

  const connectGmail = async () => {
    setBusy("gmail");
    setError(null);
    try {
      const { url, error: oauthError } = await fetchGoogleGmailOAuthUrl();
      if (!url) {
        setError(oauthError || "No se pudo iniciar OAuth Gmail.");
        return;
      }
      window.location.href = url;
    } catch {
      setError("Error al conectar Gmail.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3 rounded border border-cyan-900/40 bg-black/40 p-3">
      <p className="ced-hud-text-muted text-xs font-medium uppercase tracking-wider">
        Google Calendar y Gmail
      </p>
      <p className="ced-hud-text-muted text-[10px]">
        Conecte sus cuentas para consultar eventos y correos por voz.
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <CedButton
          type="button"
          variant={calendarConnected ? "secondary" : "primary"}
          disabled={busy !== null}
          className="w-full !text-[10px] sm:flex-1"
          onClick={() => void connectCalendar()}
        >
          {busy === "calendar"
            ? "CONECTANDO…"
            : calendarConnected
              ? "CALENDAR · CONECTADO"
              : "CONECTAR GOOGLE CALENDAR"}
        </CedButton>
        <CedButton
          type="button"
          variant={gmailConnected ? "secondary" : "primary"}
          disabled={busy !== null}
          className="w-full !text-[10px] sm:flex-1"
          onClick={() => void connectGmail()}
        >
          {busy === "gmail"
            ? "CONECTANDO…"
            : gmailConnected
              ? "GMAIL · CONECTADO"
              : "CONECTAR GMAIL"}
        </CedButton>
      </div>
      {error ? (
        <p className="text-[10px] text-red-400">{error}</p>
      ) : null}
    </div>
  );
}
