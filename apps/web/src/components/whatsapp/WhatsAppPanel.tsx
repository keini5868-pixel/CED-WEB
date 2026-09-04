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
  fetchWhatsAppMissions,
  fetchWhatsAppStatus,
  patchWhatsAppFlow,
  type WhatsAppFlow,
  type WhatsAppMessage,
  type WhatsAppMissionContact,
  type WhatsAppStatus,
  type WhatsAppTemplate,
} from "@/lib/api/whatsapp";
import { WhatsAppConnectWizard } from "@/components/whatsapp/WhatsAppConnectWizard";

export function WhatsAppPanel() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [flows, setFlows] = useState<WhatsAppFlow[]>([]);
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [missions, setMissions] = useState<WhatsAppMissionContact[]>([]);
  const [hud, setHud] = useState({ close_ready: 0, leak_risk: 0, needs_human: 0 });
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
  const [d360Key, setD360Key] = useState("");
  const [d360PhoneId, setD360PhoneId] = useState("");
  const [d360Display, setD360Display] = useState("");
  const [addonPrice, setAddonPrice] = useState(29);
  const [hubUrl, setHubUrl] = useState("https://hub.360dialog.com/");

  const refresh = useCallback(async () => {
    const [st, fl, msgs, miss] = await Promise.all([
      fetchWhatsAppStatus(),
      fetchWhatsAppFlows(),
      fetchWhatsAppMessages(),
      fetchWhatsAppMissions(),
    ]);
    if (st) {
      setStatus(st);
      setGoal(st.automation_goal || "");
      setCtaUrl(st.automation_cta_url || "");
      setCtaLabel(st.automation_cta_label || "");
      if (typeof st.addon_price_usd === "number") setAddonPrice(st.addon_price_usd);
    }
    setFlows(fl);
    setMessages(msgs);
    setMissions(miss.contacts);
    setHud(miss.hud);
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
    void fetchWhatsAppConnectConfig().then((cfg) => {
      if ("error" in cfg) return;
      if (typeof cfg.addon_price_usd === "number") setAddonPrice(cfg.addon_price_usd);
      if (cfg.d360_hub_url) setHubUrl(cfg.d360_hub_url);
    });
  }, [refresh]);

  const connect360 = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await connectWhatsApp({
        provider: "360dialog",
        api_key: d360Key.trim(),
        phone_number_id: d360PhoneId.trim() || undefined,
        display_phone: d360Display.trim() || undefined,
      });
      if (result.error) {
        setError(result.error);
        return;
      }
      if (goal.trim() || ctaUrl.trim() || ctaLabel.trim()) {
        const saved = await saveWhatsAppAutomation({
          goal,
          cta_url: ctaUrl,
          cta_label: ctaLabel,
        });
        if (saved.error) setError(saved.error);
      }
      setD360Key("");
      await refresh();
    } catch (err) {
      setError(
        err instanceof Error && err.message.trim()
          ? err.message
          : "No se pudo conectar tu WhatsApp. Revisa los datos del paso 3 e inténtalo de nuevo.",
      );
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
          WhatsApp con CED
        </h1>
        <p className="mt-1 text-sm text-[var(--ced-text-muted)]">
          Conecta tu número y deja que CED responda por ti con la misma inteligencia
          del chat. Tus clientes pueden escribir STOP para dejar de recibir mensajes.
        </p>
      </div>

      <section className="rounded border border-cyan-500/25 bg-black/40 p-4">
        {status?.connected ? (
          <div className="space-y-3">
            <div className="flex items-start gap-3 rounded-lg border border-emerald-500/40 bg-emerald-950/30 px-4 py-3">
              <span className="mt-0.5 text-lg text-emerald-400" aria-hidden>
                ●
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-emerald-100">
                  ¡Listo! Tu WhatsApp ya está conectado a CED
                </p>
                <p className="mt-1 text-xs text-emerald-200/80">
                  Funcionando · {status.display_phone || status.phone_number_id}
                  {status.verified_name ? ` · ${status.verified_name}` : ""}
                </p>
              </div>
              <button
                type="button"
                className="shrink-0 text-xs text-red-300 underline"
                onClick={async () => {
                  await disconnectWhatsApp();
                  await refresh();
                }}
              >
                Desconectar
              </button>
            </div>
          </div>
        ) : (
          <WhatsAppConnectWizard
            hubUrl={hubUrl}
            addonPrice={addonPrice}
            busy={busy}
            error={error}
            connectionKey={d360Key}
            phoneId={d360PhoneId}
            displayPhone={d360Display}
            goal={goal}
            ctaUrl={ctaUrl}
            ctaLabel={ctaLabel}
            onConnectionKeyChange={setD360Key}
            onPhoneIdChange={setD360PhoneId}
            onDisplayPhoneChange={setD360Display}
            onGoalChange={setGoal}
            onCtaUrlChange={setCtaUrl}
            onCtaLabelChange={setCtaLabel}
            onConnect={connect360}
          />
        )}
      </section>

      {status?.connected ? (
        <>
          <section className="rounded border border-cyan-500/25 bg-black/40 p-4 space-y-3">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
              TU OBJETIVO
            </h2>
            <p className="text-xs text-cyan-100/60">
              CED clasifica a cada persona y busca llevarla hacia este objetivo. Puedes
              cambiarlo cuando quieras.
            </p>
            <label className="block text-xs text-cyan-100/70">
              ¿A dónde quieres que CED guíe a quien te escriba?
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

          {error ? (
            <p className="rounded border border-red-500/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">
              {error}
            </p>
          ) : null}

          <section className="rounded border border-amber-500/30 bg-black/40 p-4 space-y-3">
            <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-amber-300">
              HUD DE INTERVENCIÓN
            </h2>
            <p className="text-xs text-cyan-100/60">
              Cierre ≥85% o duda crítica: CED te avisa para un toque humano.
              Fuga = abandono por tono, no por clics.
            </p>
            <div className="flex flex-wrap gap-3 text-xs text-cyan-100">
              <span>Listos para cerrar: {hud.close_ready}</span>
              <span>Riesgo de fuga: {hud.leak_risk}</span>
              <span>Toque humano: {hud.needs_human}</span>
            </div>
            {missions.length === 0 ? (
              <p className="text-xs text-cyan-100/50">
                Aún no hay contactos clasificados. Cuando escriban, verás su ADN
                aquí. Ejecuta en Supabase la migración 039_whatsapp_cognitive.sql
                si las columnas no existen.
              </p>
            ) : (
              <ul className="space-y-1.5 text-xs text-cyan-100/85">
                {missions.slice(0, 12).map((c) => (
                  <li
                    key={String(c.wa_from)}
                    className="flex flex-wrap gap-x-3 gap-y-0.5 border-b border-cyan-900/40 pb-1"
                  >
                    <span className="font-mono">{c.wa_from}</span>
                    <span>{c.prospect_dna}</span>
                    <span>cierre {c.close_score}%</span>
                    <span>fuga {c.leak_risk}%</span>
                    {c.human_alert ? (
                      <span className="text-amber-300">{c.human_alert}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
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
