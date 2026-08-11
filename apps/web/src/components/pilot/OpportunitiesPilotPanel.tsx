"use client";

import { ArrowLeft, ExternalLink, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  OPPORTUNITIES_WELCOME,
  fetchFitlineActionPlan,
  fetchFitlineSponsor,
  fetchOpportunitiesCatalog,
  fetchOpportunitiesPilotStatus,
  fetchOpportunityDetail,
  saveFitlineSponsor,
  type FitlineActionPlan,
  type FitlineSponsorInfo,
  type OpportunityDetail,
  type OpportunitySummary,
} from "@/lib/api/opportunitiesPilot";
import type { ModulePanelProps } from "@/modules/types";

function SectionBlock({
  title,
  body,
  attribution,
  searchUpdates,
  honestRisks,
  embed,
}: {
  title: string;
  body: string;
  attribution?: string;
  searchUpdates?: Array<{
    text: string;
    source_url?: string;
    source_title?: string;
  }>;
  honestRisks?: boolean;
  embed?: { type?: string; video_id?: string; url?: string } | null;
}) {
  const youtubeId =
    embed?.type === "youtube" && embed.video_id
      ? embed.video_id.replace(/[^a-zA-Z0-9_-]/g, "")
      : "";

  return (
    <section
      className={
        honestRisks
          ? "rounded border border-amber-500/30 bg-amber-500/5 px-2.5 py-2"
          : undefined
      }
    >
      <h3
        className={`mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] ${
          honestRisks ? "text-amber-200" : "text-cyan-300/90"
        }`}
      >
        {title}
        {attribution ? (
          <span className="ml-1 font-normal normal-case text-slate-500">
            ({attribution})
          </span>
        ) : null}
      </h3>
      {youtubeId ? (
        <div className="mb-2 aspect-video w-full overflow-hidden rounded border border-white/10 bg-black">
          <iframe
            title={`${title} — video`}
            src={`https://www.youtube-nocookie.com/embed/${youtubeId}`}
            className="h-full w-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            loading="lazy"
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      ) : null}
      <div className="whitespace-pre-wrap text-[14px] leading-[1.65] text-slate-300">
        {body}
      </div>
      {(searchUpdates || []).length > 0 ? (
        <ul className="mt-2 space-y-1.5 border-t border-white/10 pt-2">
          <li className="text-[10px] uppercase text-slate-500">
            Actualización desde búsqueda
          </li>
          {(searchUpdates || []).map((u, i) => (
            <li
              key={`${u.text.slice(0, 24)}-${i}`}
              className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-slate-300"
            >
              {u.text}
              {u.source_url ? (
                <a
                  href={u.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-0.5 block truncate text-[10px] text-cyan-500/80 hover:underline"
                >
                  {u.source_title || u.source_url}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function DetailView({
  detail,
  onBack,
}: {
  detail: OpportunityDetail;
  onBack: () => void;
}) {
  const sponsor = detail.sponsorship;
  const [sponsorInfo, setSponsorInfo] = useState<FitlineSponsorInfo | null>(
    sponsor
      ? {
          url: sponsor.url,
          configured: sponsor.configured,
          source: sponsor.source,
          has_own: sponsor.has_own,
          cta_label: sponsor.cta_label,
        }
      : null,
  );
  const [sponsorDraft, setSponsorDraft] = useState("");
  const [sponsorBusy, setSponsorBusy] = useState(false);
  const [sponsorMsg, setSponsorMsg] = useState<string | null>(null);
  const [editingLink, setEditingLink] = useState(false);
  const [plan, setPlan] = useState<FitlineActionPlan | null>(
    detail.action_plan ?? null,
  );

  useEffect(() => {
    void fetchFitlineSponsor()
      .then((s) => {
        setSponsorInfo(s);
        if (s.has_own && s.url) setSponsorDraft(s.url);
      })
      .catch(() => undefined);
    if (!detail.action_plan) {
      void fetchFitlineActionPlan()
        .then((r) => setPlan(r.plan))
        .catch(() => undefined);
    }
  }, [detail.action_plan]);

  const activeUrl = sponsorInfo?.url || sponsor?.url || "";
  const configured = Boolean(sponsorInfo?.configured ?? sponsor?.configured);
  const usingOwn = sponsorInfo?.source === "user" || Boolean(sponsorInfo?.has_own);

  const saveOwnLink = async () => {
    setSponsorBusy(true);
    setSponsorMsg(null);
    try {
      const saved = await saveFitlineSponsor(sponsorDraft.trim());
      setSponsorInfo(saved);
      setEditingLink(false);
      setSponsorMsg(
        saved.has_own
          ? "Tu enlace de patrocinio quedó guardado. CED lo usará para atraer a tus socios."
          : "Se restauró el enlace por defecto de CED.",
      );
    } catch (e) {
      setSponsorMsg(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setSponsorBusy(false);
    }
  };

  const goals = plan?.content?.goals || [];
  const steps = plan?.content?.steps || [];

  return (
    <div className="space-y-6 text-[14px] leading-[1.65] text-slate-200">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-cyan-400 hover:text-cyan-200"
      >
        <ArrowLeft className="h-4 w-4" />
        Volver al listado
      </button>

      <header>
        <h2 className="font-[family-name:var(--font-orbitron)] text-lg font-semibold tracking-wide text-cyan-100 sm:text-xl">
          {detail.title}
        </h2>
        {detail.tagline ? (
          <p className="mt-2 text-sm leading-relaxed text-slate-400">{detail.tagline}</p>
        ) : null}
        {detail.curated_as_of ? (
          <p className="mt-1 text-[10px] text-slate-500">
            Base curada: {detail.curated_as_of}
          </p>
        ) : null}
      </header>

      {(detail.sections || []).map((s) => (
        <SectionBlock
          key={s.id}
          title={s.title}
          body={s.body}
          attribution={s.attribution}
          searchUpdates={s.search_updates}
          honestRisks={s.honest_risks}
          embed={s.embed}
        />
      ))}

      {plan ? (
        <section className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 px-4 py-3.5">
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-emerald-200">
            Plan de crecimiento de tu franquicia
          </h3>
          <p className="mb-2 text-sm text-slate-300">{plan.title}</p>
          {goals.length > 0 ? (
            <div className="mb-2">
              <p className="text-[11px] uppercase text-slate-500">Metas</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-slate-300">
                {goals.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {steps.length > 0 ? (
            <div>
              <p className="text-[11px] uppercase text-slate-500">Pasos</p>
              <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-sm text-slate-300">
                {steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            </div>
          ) : null}
          {plan.content?.notes ? (
            <p className="mt-2 text-sm text-slate-400">{plan.content.notes}</p>
          ) : null}
        </section>
      ) : null}

      <section className="rounded-xl border border-cyan-500/25 bg-cyan-500/5 px-4 py-3.5">
        <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-cyan-200">
          Activar franquicia
        </h3>
        {configured && activeUrl ? (
          <div className="space-y-2">
            <a
              href={activeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-600/90 px-4 py-3 text-sm font-semibold text-white hover:bg-cyan-500"
            >
              {sponsorInfo?.cta_label ||
                sponsor?.cta_label ||
                "Activar su franquicia (paquete manager)"}
              <ExternalLink className="h-4 w-4" />
            </a>
            <div className="flex flex-wrap items-center gap-2">
              <p className="min-w-0 flex-1 truncate text-[11px] text-slate-500" title={activeUrl}>
                {activeUrl}
              </p>
              <button
                type="button"
                onClick={() => {
                  setEditingLink(true);
                  setSponsorDraft(usingOwn ? activeUrl : "");
                  setSponsorMsg(null);
                }}
                className="shrink-0 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1 text-[12px] font-medium text-cyan-200 hover:bg-cyan-500/20"
              >
                Editar enlace
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm leading-relaxed text-amber-100/90">
            El enlace de patrocinio aún no está configurado. Cuando esté listo,
            aparecerá aquí el botón para activar tu franquicia.
          </p>
        )}
        {usingOwn ? (
          <p className="mt-2 text-[11px] text-emerald-300/90">
            Estás usando tu propio enlace de patrocinio.
          </p>
        ) : sponsorInfo?.has_default ? (
          <p className="mt-2 text-[11px] text-slate-500">
            Enlace por defecto de CED. Cuando actives tu franquicia, pulsa{" "}
            <span className="text-slate-300">Editar enlace</span> y pega el tuyo
            para atraer a tus propios socios.
          </p>
        ) : null}
      </section>

      {editingLink ? (
        <section className="rounded-xl border border-white/10 bg-black/20 px-4 py-3.5">
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-slate-300">
            Editar enlace de patrocinio
          </h3>
          <p className="mb-3 text-[12px] leading-relaxed text-slate-500">
            Por defecto se muestra el enlace de CED. Si ya te inscribiste con ese
            enlace, pega aquí el tuyo: CED lo usará cuando invites a nuevas
            personas desde Oportunidades.
          </p>
          <input
            type="url"
            value={sponsorDraft}
            onChange={(e) => setSponsorDraft(e.target.value)}
            placeholder="https://…"
            className="mb-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500/50"
            autoFocus
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={sponsorBusy}
              onClick={() => void saveOwnLink()}
              className="rounded-lg bg-cyan-700/80 px-3 py-1.5 text-sm text-white hover:bg-cyan-600 disabled:opacity-50"
            >
              {sponsorBusy ? "Guardando…" : "Guardar mi enlace"}
            </button>
            <button
              type="button"
              disabled={sponsorBusy}
              onClick={() => {
                setSponsorDraft("");
                void (async () => {
                  setSponsorBusy(true);
                  try {
                    const saved = await saveFitlineSponsor("");
                    setSponsorInfo(saved);
                    setEditingLink(false);
                    setSponsorMsg("Se restauró el enlace por defecto de CED.");
                  } catch (e) {
                    setSponsorMsg(e instanceof Error ? e.message : "Error");
                  } finally {
                    setSponsorBusy(false);
                  }
                })();
              }}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-slate-300 hover:bg-white/5 disabled:opacity-50"
            >
              Usar enlace CED
            </button>
            <button
              type="button"
              disabled={sponsorBusy}
              onClick={() => {
                setEditingLink(false);
                setSponsorMsg(null);
              }}
              className="rounded-lg px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200"
            >
              Cancelar
            </button>
          </div>
          {sponsorMsg ? (
            <p className="mt-2 text-[12px] text-cyan-300/90">{sponsorMsg}</p>
          ) : null}
        </section>
      ) : sponsorMsg ? (
        <p className="text-[12px] text-cyan-300/90">{sponsorMsg}</p>
      ) : null}

      {(detail.data_gaps || []).length > 0 ? (
        <section className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5">
          <h3 className="mb-1 text-[11px] font-semibold text-amber-200">
            Limitaciones de datos
          </h3>
          <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-amber-100/80">
            {(detail.data_gaps || []).map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {(detail.sources?.curated || []).length > 0 ? (
        <section>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Fuentes base
          </h3>
          <ul className="space-y-1 text-[10px]">
            {(detail.sources?.curated || []).map((s) => (
              <li key={s.url || s.title}>
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-cyan-500/80 hover:underline"
                  >
                    {s.title || s.url}
                  </a>
                ) : (
                  <span className="text-slate-500">{s.title}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function OpportunitiesModuleContent(_props: ModulePanelProps) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [catalog, setCatalog] = useState<OpportunitySummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);

  useEffect(() => {
    void fetchOpportunitiesPilotStatus().then((s) =>
      setConfigured(s?.enabled ?? null),
    );
    void fetchOpportunitiesCatalog()
      .then(setCatalog)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "No se pudo cargar el catálogo."),
      );
  }, []);

  const openDetail = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      const d = await fetchOpportunityDetail(id);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar la ficha.");
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-8 sm:py-6">
        {!detail ? (
          <>
            <p className="text-sm leading-relaxed text-slate-400">
              {OPPORTUNITIES_WELCOME}
            </p>
            {configured === false ? (
              <p className="text-sm text-red-300">
                OPPORTUNITIES_MODULE_ENABLED desactivado en la API.
              </p>
            ) : null}
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            <ul className="space-y-3">
              {catalog.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void openDetail(item.id)}
                    className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3.5 text-left transition hover:border-cyan-500/40 disabled:opacity-60"
                  >
                    <div className="text-[15px] font-semibold tracking-wide text-cyan-100">
                      {item.title}
                    </div>
                    <div className="mt-1.5 text-sm leading-relaxed text-slate-400">
                      {item.tagline}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            {busy ? (
              <p className="inline-flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Cargando ficha…
              </p>
            ) : null}
          </>
        ) : (
          <>
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            <DetailView detail={detail} onBack={() => setDetail(null)} />
          </>
        )}
      </div>
    </div>
  );
}
