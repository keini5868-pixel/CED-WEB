"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectWhatsApp,
  createWhatsAppFlow,
  deleteWhatsAppFlow,
  disconnectWhatsApp,
  createWhatsAppTemplate,
  sendWhatsAppTemplate,
  sendWhatsAppText,
  fetchWhatsAppTemplates,
  saveWhatsAppAutomation,
  fetchWhatsAppConnectConfig,
  fetchWhatsAppFlows,
  fetchWhatsAppMessages,
  fetchWhatsAppStatus,
  patchWhatsAppFlow,
  type WhatsAppFlow,
  type WhatsAppMessage,
  type WhatsAppStatus,
  type WhatsAppTemplate,
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

function facebookApiVersion(raw: string): string {
  const v = (raw || "v21.0").trim();
  return v.startsWith("v") ? v : `v${v}`;
}

function loadFacebookSdk(appId: string, apiVersion: string): Promise<void> {
  const version = facebookApiVersion(apiVersion);
  const init = () => {
    if (!window.FB) {
      throw new Error("Facebook SDK no disponible");
    }
    window.FB.init({
      appId,
      cookie: true,
      xfbml: false,
      version,
    });
  };
  if (window.FB) {
    init();
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const ok = () => {
      if (settled) return;
      settled = true;
      try {
        init();
        resolve();
      } catch (err) {
        reject(err);
      }
    };
    const fail = (message: string) => {
      if (settled) return;
      settled = true;
      reject(new Error(message));
    };
    window.fbAsyncInit = ok;
    if (!document.getElementById("facebook-jssdk")) {
      const script = document.createElement("script");
      script.id = "facebook-jssdk";
      script.src = "https://connect.facebook.net/en_US/sdk.js";
      script.async = true;
      script.onerror = () =>
        fail(
          "No se pudo cargar el SDK de Facebook (bloqueo del navegador o red). Desactiva el bloqueador en ced-castillo.com e inténtalo de nuevo.",
        );
      document.body.appendChild(script);
    }
    window.setTimeout(() => {
      if (window.FB) ok();
      else
        fail(
          "El SDK de Facebook no cargó. En la app de Meta: Facebook Login → Settings → activa Login with the JavaScript SDK y añade ced-castillo.com en Allowed Domains.",
        );
    }, 8000);
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
  const [sendTo, setSendTo] = useState("");
  const [sendBody, setSendBody] = useState("Hola, te escribe CED.");
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [tplName, setTplName] = useState("hello_ced");
  const [tplLang, setTplLang] = useState("es");
  const [tplCat, setTplCat] = useState("UTILITY");
  const [tplBody, setTplBody] = useState("Hola {{1}}, CED confirma tu mensaje. Responde para continuar.");
  const [tplSendName, setTplSendName] = useState("hello_world");
  const [tplSendLang, setTplSendLang] = useState("en_US");
  const [tplSendTo, setTplSendTo] = useState("");
  const [tplParam, setTplParam] = useState("");
  const [goal, setGoal] = useState("");
  const [ctaUrl, setCtaUrl] = useState("");
  const [ctaLabel, setCtaLabel] = useState("");

  const refresh = useCallback(async () => {
    const [st, fl, msgs] = await Promise.all([
      fetchWhatsAppStatus(),
      fetchWhatsAppFlows(),
      fetchWhatsAppMessages(),
    ]);
    if (st) {
      setStatus(st);
      setGoal(st.automation_goal || "");
      setCtaUrl(st.automation_cta_url || "");
      setCtaLabel(st.automation_cta_label || "");
    }
    setFlows(fl);
    setMessages(msgs);
    if (st?.connected) {
      try {
        const t = await fetchWhatsAppTemplates();
        setTemplates(t);
      } catch {
        setTemplates([]);
      }
    } else {
      setTemplates([]);
    }
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
          "Falta el config_id de WhatsApp Embedded Signup. En developers.facebook.com → tu app (tipo Business) → Facebook Login for Business → Configurations → Create from template → “WhatsApp Embedded Signup Configuration With 60 Expiration Token”. Copia el Configuration ID. En Railway, servicio API (no web), variable WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID. Redeploy y vuelve a Conectar.",
        );
        return;
      }

      let wabaId = "";
      let phoneNumberId = "";
      const onMessage = (event: MessageEvent) => {
        if (
          event.origin !== "https://www.facebook.com" &&
          event.origin !== "https://web.facebook.com" &&
          !event.origin.endsWith(".facebook.com")
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
      const appId = cfg.app_id || cfg.app_id;
      const apiVersion = cfg.api_version || cfg.api_version;
      const configId = cfg.config_id || cfg.config_id;
      if (!appId) {
        setError("META_APP_ID no llegó desde la API. Revísalo en Railway (servicio API).");
        return;
      }
      await loadFacebookSdk(appId, apiVersion);
      if (!window.FB) {
        setError(
          "Facebook SDK no está listo. Añade ced-castillo.com en Allowed Domains for the JavaScript SDK.",
        );
        return;
      }
      await new Promise<void>((resolve) => {
        window.FB.login(
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
            config_id: configId,
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
    } catch (err) {
      const message =
        err instanceof Error && err.message.trim()
          ? err.message
          : "Error al conectar WhatsApp.";
      setError(message);
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
      reply_text: trigger === "ced_ai" ? "__CED_AI__" : reply.trim(),
      enabled: true,
      priority: trigger === "catch_all" ? 900 : trigger === "ced_ai" ? 50 : 50,
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
          Conecta el número, envía mensajes, administra plantillas de Meta y deja
          que CED responda WhatsApp con el mismo conocimiento que el chat (si no
          hay una palabra clave). El cliente escribe STOP para salir.
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
              OBJETIVO DE LA AUTOMATIZACIÓN
            </h2>
            <p className="text-xs text-cyan-100/60">
              Cada cuenta CED conecta su propio número. Cuando alguien responde a
              tu campaña, CED usa el mismo cerebro del chat y guía hacia lo que
              definas aquí (grupo, enlace, llamada, etc.). Si tienes un flujo de
              palabra clave como “hola”, páusalo para que no pise esta conversación.
            </p>
            <label className="block text-xs text-cyan-100/70">
              ¿A qué quieres llevar a quien te escriba?
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                placeholder="Ej. Invitar al grupo de WhatsApp de onboarding y, si preguntan, agendar una llamada."
              />
            </label>
            <label className="block text-xs text-cyan-100/70">
              Enlace o grupo (opcional)
              <input
                value={ctaUrl}
                onChange={(e) => setCtaUrl(e.target.value)}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                placeholder="https://chat.whatsapp.com/..."
              />
            </label>
            <label className="block text-xs text-cyan-100/70">
              Cómo llamas a ese enlace (opcional)
              <input
                value={ctaLabel}
                onChange={(e) => setCtaLabel(e.target.value)}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                placeholder="Grupo de onboarding"
              />
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError(null);
                  const result = await saveWhatsAppAutomation({
                    goal,
                    cta_url: ctaUrl,
                    cta_label: ctaLabel,
                  });
                  setBusy(false);
                  if (result.error) {
                    setError(result.error);
                    return;
                  }
                  await refresh();
                })();
              }}
              className="rounded border border-cyan-400/60 px-3 py-2 text-xs font-bold tracking-wider text-cyan-100 disabled:opacity-40"
            >
              GUARDAR OBJETIVO
            </button>
          </section>

          <section className="rounded border border-cyan-500/25 bg-black/40 p-4 space-y-3">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
              ENVIAR MENSAJE
            </h2>
            <p className="text-xs text-cyan-100/60">
              Texto libre solo funciona dentro de la ventana de 24 h (después de que el
              cliente te escriba). Fuera de esa ventana usa una plantilla aprobada.
            </p>
            <label className="block text-xs text-cyan-100/70">
              Número destino (con código de país, sin +)
              <input
                value={sendTo}
                onChange={(e) => setSendTo(e.target.value)}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                placeholder="18095551234"
              />
            </label>
            <label className="block text-xs text-cyan-100/70">
              Texto
              <textarea
                value={sendBody}
                onChange={(e) => setSendBody(e.target.value)}
                rows={2}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
              />
            </label>
            <button
              type="button"
              disabled={busy || !sendTo.trim() || !sendBody.trim()}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError(null);
                  const result = await sendWhatsAppText(sendTo, sendBody);
                  setBusy(false);
                  if (result.error) {
                    setError(result.error);
                    return;
                  }
                  await refresh();
                })();
              }}
              className="rounded border border-cyan-400/60 px-3 py-2 text-xs font-bold tracking-wider text-cyan-100 disabled:opacity-40"
            >
              ENVIAR TEXTO
            </button>
          </section>

          <section className="rounded border border-cyan-500/25 bg-black/40 p-4 space-y-3">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
              PLANTILLAS
            </h2>
            {templates.length === 0 ? (
              <p className="text-xs text-cyan-100/60">
                No hay plantillas en esta WABA todavía. Crea una (queda en revisión de
                Meta) o usa hello_world si Meta te la dio de ejemplo.
              </p>
            ) : (
              <ul className="space-y-1 text-xs text-cyan-100/80">
                {templates.map((tpl, idx) => (
                  <li key={`${tpl.name}-${tpl.language}-${idx}`}>
                    {tpl.name} · {tpl.language || "?"} · {tpl.status || "?"} ·{" "}
                    {tpl.category || ""}
                  </li>
                ))}
              </ul>
            )}
            <label className="block text-xs text-cyan-100/70">
              Nombre nuevo
              <input
                value={tplName}
                onChange={(e) => setTplName(e.target.value)}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs text-cyan-100/70">
                Idioma
                <input
                  value={tplLang}
                  onChange={(e) => setTplLang(e.target.value)}
                  className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                />
              </label>
              <label className="block text-xs text-cyan-100/70">
                Categoría
                <input
                  value={tplCat}
                  onChange={(e) => setTplCat(e.target.value)}
                  className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                />
              </label>
            </div>
            <label className="block text-xs text-cyan-100/70">
              Cuerpo (usa {"{{1}}"} si necesitas un parámetro)
              <textarea
                value={tplBody}
                onChange={(e) => setTplBody(e.target.value)}
                rows={2}
                className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
              />
            </label>
            <button
              type="button"
              disabled={busy || !tplName.trim() || !tplBody.trim()}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError(null);
                  const result = await createWhatsAppTemplate({
                    name: tplName,
                    language: tplLang,
                    body: tplBody,
                    category: tplCat,
                  });
                  setBusy(false);
                  if (result.error) {
                    setError(result.error);
                    return;
                  }
                  await refresh();
                })();
              }}
              className="rounded border border-cyan-400/60 px-3 py-2 text-xs font-bold tracking-wider text-cyan-100 disabled:opacity-40"
            >
              CREAR PLANTILLA
            </button>
            <div className="border-t border-cyan-800/40 pt-3 space-y-2">
              <p className="text-xs text-cyan-100/70">Enviar plantilla aprobada</p>
              <label className="block text-xs text-cyan-100/70">
                Destino
                <input
                  value={tplSendTo}
                  onChange={(e) => setTplSendTo(e.target.value)}
                  className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="block text-xs text-cyan-100/70">
                  Nombre
                  <input
                    value={tplSendName}
                    onChange={(e) => setTplSendName(e.target.value)}
                    className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                  />
                </label>
                <label className="block text-xs text-cyan-100/70">
                  Idioma
                  <input
                    value={tplSendLang}
                    onChange={(e) => setTplSendLang(e.target.value)}
                    className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                  />
                </label>
              </div>
              <label className="block text-xs text-cyan-100/70">
                Parámetro {"{{1}}"} (opcional)
                <input
                  value={tplParam}
                  onChange={(e) => setTplParam(e.target.value)}
                  className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                />
              </label>
              <button
                type="button"
                disabled={busy || !tplSendTo.trim() || !tplSendName.trim()}
                onClick={() => {
                  void (async () => {
                    setBusy(true);
                    setError(null);
                    const result = await sendWhatsAppTemplate({
                      to: tplSendTo,
                      name: tplSendName,
                      language: tplSendLang,
                      body_params: tplParam.trim() ? [tplParam.trim()] : [],
                    });
                    setBusy(false);
                    if (result.error) {
                      setError(result.error);
                      return;
                    }
                    await refresh();
                  })();
                }}
                className="rounded border border-cyan-400/60 px-3 py-2 text-xs font-bold tracking-wider text-cyan-100 disabled:opacity-40"
              >
                ENVIAR PLANTILLA
              </button>
            </div>
          </section>

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
                <option value="ced_ai">CED chat (conocimiento)</option>
                <option value="catch_all">Texto fijo (cualquier otro)</option>
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
            {trigger === "ced_ai" ? (
              <p className="text-xs text-cyan-100/60">
                CED responde con el mismo conocimiento que el chat del dashboard.
              </p>
            ) : (
              <label className="block text-xs text-cyan-100/70">
                Respuesta
                <textarea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-2 py-1.5 text-sm text-cyan-50"
                />
              </label>
            )}
            <button
              type="button"
              onClick={() => void addFlow()}
              disabled={trigger !== "ced_ai" && !reply.trim()}
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
                          ? "Cualquier mensaje (texto fijo)"
                          : flow.trigger_type === "ced_ai" || flow.trigger_type === "ai"
                            ? "CED chat"
                            : `Claves: ${flow.keywords}`}
                      </p>
                      {flow.trigger_type === "ced_ai" || flow.trigger_type === "ai" ? (
                        <p className="mt-1 text-cyan-50/90">
                          Responde como el chat de CED
                        </p>
                      ) : (
                        <p className="mt-1 text-cyan-50/90">{flow.reply_text}</p>
                      )}
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
