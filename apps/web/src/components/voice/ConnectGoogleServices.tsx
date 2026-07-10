"use client";

import { useCallback, useEffect, useState } from "react";

import { CedButton } from "@ced/ui";

import {
  connectGoogleViaSupabase,
  fetchGoogleCalendarStatus,
  fetchGoogleGmailStatus,
  syncPendingGoogleProviderToken,
} from "@/lib/api/google";

export const GOOGLE_CALENDAR_CONNECTED_EVENT = "ced:google-calendar-connected";
export const GOOGLE_GMAIL_CONNECTED_EVENT = "ced:google-gmail-connected";

const SUCCESS_MESSAGES = {
  calendar: "Google Calendar conectado correctamente.",
  gmail: "Gmail conectado correctamente.",
} as const;

export function GoogleOAuthCallbackBanner() {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const calendarParam = params.get("calendar");
        if (calendarParam === "connected") {
          setMessage(SUCCESS_MESSAGES.calendar);
          window.dispatchEvent(new Event(GOOGLE_CALENDAR_CONNECTED_EVENT));
          params.delete("calendar");
          const next = `${window.location.pathname}${
            params.toString() ? `?${params.toString()}` : ""
          }`;
          window.history.replaceState({}, "", next);
          return;
        }
        if (calendarParam === "error" || calendarParam?.startsWith("scope")) {
          setMessage(
            "No se pudieron obtener permisos de Calendar. Pulse «Reconectar Calendar» y acepte todos los permisos.",
          );
          params.delete("calendar");
          const next = `${window.location.pathname}${
            params.toString() ? `?${params.toString()}` : ""
          }`;
          window.history.replaceState({}, "", next);
          return;
        }
      }

      const result = await syncPendingGoogleProviderToken();
      if (cancelled || !result.type) return;

      if (result.ok) {
        setMessage(SUCCESS_MESSAGES[result.type]);
        window.dispatchEvent(
          new Event(
            result.type === "calendar"
              ? GOOGLE_CALENDAR_CONNECTED_EVENT
              : GOOGLE_GMAIL_CONNECTED_EVENT,
          ),
        );
        return;
      }

      setMessage(
        result.error ||
          (result.type === "calendar"
            ? "No se pudo conectar Google Calendar."
            : "No se pudo conectar Gmail."),
      );
    })();

    return () => {
      cancelled = true;
    };
  }, []);

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
    setCalendarConnected(Boolean(cal?.connected));
    setGmailConnected(Boolean(mail?.connected));
  }, []);

  useEffect(() => {
    void refresh();
    const onCal = () => {
      setCalendarConnected(true);
      void refresh();
    };
    const onMail = () => {
      setGmailConnected(true);
      void refresh();
    };
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
    const { error: oauthError } = await connectGoogleViaSupabase("calendar");
    if (oauthError) {
      setError(oauthError);
      setBusy(null);
    }
  };

  const connectGmail = async () => {
    setBusy("gmail");
    setError(null);
    const { error: oauthError } = await connectGoogleViaSupabase("gmail");
    if (oauthError) {
      setError(oauthError);
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
              ? "📅 CALENDAR · CONECTADO"
              : "📅 Conectar Google Calendar"}
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
              ? "📧 GMAIL · CONECTADO"
              : "📧 Conectar Gmail"}
        </CedButton>
      </div>
      {error ? (
        <p className="text-[10px] text-red-400">{error}</p>
      ) : null}
    </div>
  );
}
