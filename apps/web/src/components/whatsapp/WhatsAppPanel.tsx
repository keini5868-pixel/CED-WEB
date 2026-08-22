"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectWhatsApp,
  createWhatsAppFlow,
  deleteWhatsAppFlow,
  disconnectWhatsApp,
  fetchWhatsAppConnectConfig,
  fetchWhatsAppFlows,
  fetchWhatsAppMessages,
  fetchWhatsAppStatus,
  patchWhatsAppFlow,
  type WhatsAppFlow,
  type WhatsAppMessage,
  type WhatsAppStatus,
} from "@/lib/api/whatsapp";

type FbAuth = {
  authResponse?: { code?: string };
};

declare global {
  interface Window {
    FB?: {
      init: (opts: Record<string, unknown>) => void;
      login: (
        cb: (res: FbAuth) => void,
        opts: Record<string, unknown>,
      ) => void;
    };
    fbAsyncInit?: () => void;
  }
}

function loadFacebookSdk(appId: string, apiVersion: string): Promise<void> {
  if (window.FB) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB?.init({
        appId,
        cookie: true,
        xfbml: false,
        version: apiVersion.replace(/^v/, "") ? apiVersion : "v21.0",
      });
      resolve();
    };
    const existing = document.getElementById("facebook-jssdk");
    if (existing) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.id = "facebook-jssdk";
    script.src = "https://connect.facebook.net/es_LA/sdk.js";
    script.async = true;
    script.onerror = () => reject(new Error("No se pudo cargar Facebook SDK"));
    document.body.appendChild(script);
    window.setTimeout(() => {
      if (window.FB) resolve();
    }, 4000);
  });
}

export function WhatsAppPanel() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [flows, setFlows] = useState<WhatsAppFlow[]>([]);
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("Precio");
  const [keywords, setKeywords] = useState("precio, costos, cuanto");
  const [reply, setReply] = useState("");
  const [trigger, setTrigger] = useState("keyword");

  const refresh = useCallback(async () => {
    const [st, fl, msgs] = await Promise.all([
      fetchWhatsAppStatus(),
      fetchWhatsAppFlows(),
      fetchWhatsAppMessages(),
    ]);
    if (st) setStatus(st);
    setFlows(fl);
    setMessages(msgs);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const cfg = await fetchWhatsAppConnectConfig();
      if ("error" in cfg) {
        setError(cfg.error);
        return;
      }
      if (!cfg.config_id) {
        setError(
          "Falta WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID en la API. Crea un Facebook Login for Business con producto WhatsApp y pega el config_id en Railway.",
        );
        return;
      }

      let wabaId = "";
      let phoneNumberId = "";
      const onMessage = (event: MessageEvent) => {
        if (
          event.origin !== "https://www.facebook.com" &&
          event.origin !== "https://web.facebook.com"
        ) {
          return;
        }
        try {
          const data = JSON.parse(String(event.data));
          if (data.type !== "WA_EMBEDDED_SIGNUP") return;
          const info = data.data || {};
          wabaId = String(info.waba_id || info.wabaId || "");
          phoneNumberId = String(
            info.phone_number_id || info.phoneNumberId || "",
          );
        } catch {
          /* ignore */
        }
      };
      window.addEventListener("message", onMessage);
      await loadFacebookSdk(cfg.app_id, cfg.api_version);
      await new Promise<void>((resolve) => {
        window.FB?.login(
          async (res) => {
            const code = res.authResponse?.code;
            window.removeEventListener("message", onMessage);
            if (!code && !wabaId) {
              setError("No se completó el alta de WhatsApp en Meta.");
              resolve();
              return;
            }
            const result = await connectWhatsApp({
              code: code || undefined,
              waba_id: wabaId || undefined,
              phone_number_id: phoneNumberId || undefined,
            });
            if (result.error) setError(result.error);
            await refresh();
            resolve();
          },
          {
            config_id: cfg.config_id,
            response_type: "code",
            override_default_response_type: true,
            extras: {
              setup: {},
              featureType: "",
              sessionInfoVersion: "3",
            },
          },
        );
      });
    } catch {
      setError("Error al conectar WhatsApp.");
    } finally {
      setBusy(false);
    }
  };

  const addFlow = async () => {
    setError(null);
    const result = await createWhatsAppFlow({
      name: name.trim() || "Flujo",
      trigger_type: trigger,
      keywords,
      reply_text: reply.trim(),
      enabled: true,
      priority: trigger === "catch_all" ? 900 : 50,
    });
    if (result.error) {
      setError(result.error);
      return;
    }
    setReply("");
    await refresh();
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-6">
      <div>
        <h1 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wide text-[var(--ced-text-primary)] sm:text-xl">
          WhatsApp
        </h1>
        <p className="mt-1 text-sm text-[var(--ced-text-muted)]">
          Conecta un número de negocio (Meta Cloud API) y define respuestas
          automáticas por palabra clave. El cliente escribe STOP para salir.
        </p>
      </div>

      <section className="rounded border border-cyan-500/25 bg-black/40 p-4">
        {status?.connected ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-emerald-200">
              Conectado: {status.display_phone || status.phone_number_id}
              {status.verified_name ? ` · ${status.verified_name}` : ""}
            </p>
            <button
              type="button"
              className="text-xs text-red-300 underline"
              onClick={async () => {
                await disconnectWhatsApp();
                await refresh();
              }}
            >
              Desconectar
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-cyan-100/80">
              El número debe ser de WhatsApp Business (no el personal del
              teléfono, salvo que lo migres a la API).
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void connect()}
              className="rounded border border-cyan-400/60 bg-cyan-950/50 px-3 py-2 text-xs font-bold tracking-wider text-cyan-100"
            >
              {busy ? "CONECTANDO…" : "CONECTAR NÚMERO"}
            </button>
          </div>
        )}
        {error ? <p className="mt-3 text-xs text-red-400">{error}</p> : null}
      </section>

      {status?.connected ? (
        <>
          <section className="rounded border border-cyan-500/25 bg-black/40 p-4 space-y-3">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
              NUEVO FLUJO
            </h2>
            <label className="block text-xs text-cyan-100/70">
              Nombre
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
              />
            </label>
            <label className="block text-xs text-cyan-100/70">
              Tipo
              <select
                value={trigger}
                onChange={(e) => setTrigger(e.target.value)}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
              >
                <option value="keyword">Palabra clave</option>
                <option value="catch_all">Cualquier otro mensaje</option>
              </select>
            </label>
            {trigger === "keyword" ? (
              <label className="block text-xs text-cyan-100/70">
                Palabras clave (separadas por coma)
                <input
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                />
              </label>
            ) : null}
            <label className="block text-xs text-cyan-100/70">
              Respuesta
              <textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
              />
            </label>
            <button
              type="button"
              onClick={() => void addFlow()}
              disabled={!reply.trim()}
              className="rounded border border-cyan-400/60 px-3 py-2 text-xs font-bold tracking-wider text-cyan-100 disabled:opacity-40"
            >
              GUARDAR FLUJO
            </button>
          </section>

          <section className="space-y-2">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
              FLUJOS
            </h2>
            {flows.length === 0 ? (
              <p className="text-sm text-cyan-100/60">Aún no hay flujos.</p>
            ) : (
              flows.map((flow) => (
                <div
                  key={flow.id}
                  className="rounded border border-cyan-800/40 bg-black/30 p-3 text-sm text-cyan-100"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium">{flow.name}</p>
                      <p className="text-xs text-cyan-100/60">
                        {flow.trigger_type === "catch_all"
                          ? "Cualquier mensaje"
                          : `Claves: ${flow.keywords}`}
                      </p>
                      <p className="mt-1 text-cyan-50/90">{flow.reply_text}</p>
                    </div>
                    <div className="flex shrink-0 flex-col gap-1">
                      <button
                        type="button"
                        className="text-[11px] text-cyan-300"
                        onClick={() =>
                          void patchWhatsAppFlow(flow.id, {
                            enabled: !flow.enabled,
                          }).then(() => refresh())
                        }
                      >
                        {flow.enabled ? "Pausar" : "Activar"}
                      </button>
                      <button
                        type="button"
                        className="text-[11px] text-red-300"
                        onClick={() =>
                          void deleteWhatsAppFlow(flow.id).then(() => refresh())
                        }
                      >
                        Borrar
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </section>

          <section className="space-y-2">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
              ÚLTIMOS MENSAJES
            </h2>
            {messages.length === 0 ? (
              <p className="text-sm text-cyan-100/60">Sin mensajes aún.</p>
            ) : (
              messages.map((msg) => (
                <p key={msg.id} className="text-xs text-cyan-100/80">
                  <span className="text-cyan-400">
                    {msg.direction === "in" ? "Cliente" : "CED"}
                  </span>{" "}
                  {msg.body}
                </p>
              ))
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
