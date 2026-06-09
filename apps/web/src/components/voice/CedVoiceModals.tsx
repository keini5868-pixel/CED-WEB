"use client";

import { useEffect, useState } from "react";

import { CedButton, CedModal } from "@ced/ui";
import type { VoicePaletteId, VoiceSessionPreferences } from "@ced/types";

import {
  listConversations,
  type ConversationRow,
} from "@/lib/api/conversations";
import { listSessionPdfs, pdfDownloadUrl, type PdfArtifact } from "@/lib/api/pdf";
import { GEMINI_VOICE_OPTIONS } from "@/lib/voice/geminiVoices";

export function CedStopConfirmModal({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <CedModal
      open={open}
      onClose={onClose}
      title="DETENER SESIÓN"
      footer={
        <>
          <CedButton variant="ghost" onClick={onClose}>
            CANCELAR
          </CedButton>
          <CedButton variant="danger" onClick={onConfirm}>
            DETENER
          </CedButton>
        </>
      }
    >
      <p className="ced-hud-text-body">
        ¿Cerrar la sesión Gemini Live? Perderás el contexto de voz actual.
      </p>
    </CedModal>
  );
}

export function CedSettingsModal({
  open,
  onClose,
  prefs,
  onSave,
  micOn,
  onApplyVoice,
}: {
  open: boolean;
  onClose: () => void;
  prefs: VoiceSessionPreferences;
  onSave: (p: VoiceSessionPreferences) => void;
  micOn: boolean;
  onApplyVoice: (voiceName: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(prefs);
  const [applyingVoice, setApplyingVoice] = useState(false);

  useEffect(() => {
    if (open) setDraft(prefs);
  }, [open, prefs]);

  const voiceChanged = draft.voiceName !== prefs.voiceName;

  return (
    <CedModal
      open={open}
      onClose={onClose}
      title="CONFIGURACIÓN DE VOZ"
      footer={
        <>
          <CedButton variant="ghost" onClick={onClose}>
            CERRAR
          </CedButton>
          <CedButton
            onClick={() => {
              onSave(draft);
              onClose();
            }}
          >
            GUARDAR PREFS
          </CedButton>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <span className="ced-hud-text-muted text-xs">
            Voz Gemini Live (requiere reiniciar sesión)
          </span>
          <p className="ced-hud-text-muted mt-1 text-[10px]">
            Activa: <strong className="text-cyan-400">{prefs.voiceName}</strong>
            {micOn
              ? " · Pulsa APLICAR VOZ para oír el cambio"
              : " · Se aplicará al activar MIC"}
          </p>
          <div className="mt-2 grid max-h-48 grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3">
            {GEMINI_VOICE_OPTIONS.map((voice) => (
              <button
                key={voice.id}
                type="button"
                onClick={() =>
                  setDraft((d) => ({ ...d, voiceName: voice.id }))
                }
                className={`rounded border px-2 py-2 text-left text-xs transition-colors ${
                  draft.voiceName === voice.id
                    ? "border-cyan-400 bg-cyan-950/40 text-cyan-200"
                    : "border-cyan-900/50 bg-black text-zinc-300 hover:border-cyan-700"
                }`}
              >
                <div className="font-medium">{voice.name}</div>
                <div className="text-[10px] text-zinc-500">
                  {voice.gender} · {voice.style}
                </div>
              </button>
            ))}
          </div>
          <CedButton
            className="mt-3 w-full"
            disabled={!voiceChanged || applyingVoice}
            onClick={() => {
              void (async () => {
                setApplyingVoice(true);
                try {
                  await onApplyVoice(draft.voiceName);
                  onSave({ ...draft, voiceName: draft.voiceName });
                } finally {
                  setApplyingVoice(false);
                }
              })();
            }}
          >
            {applyingVoice
              ? "CAMBIANDO VOZ…"
              : micOn
                ? "APLICAR VOZ"
                : "GUARDAR VOZ (próxima sesión)"}
          </CedButton>
        </div>

        <label className="block">
          <span className="ced-hud-text-muted text-xs">Idioma (UI)</span>
          <select
            className="mt-1 w-full rounded border border-cyan-700/50 bg-black px-3 py-2 text-sm text-white"
            value={draft.language}
            onChange={(e) =>
              setDraft({
                ...draft,
                language: e.target.value as VoiceSessionPreferences["language"],
              })
            }
          >
            <option value="es">Español</option>
            <option value="en">English</option>
            <option value="pt">Português</option>
          </select>
        </label>
        <label className="block">
          <span className="ced-hud-text-muted text-xs">Velocidad</span>
          <select
            className="mt-1 w-full rounded border border-cyan-700/50 bg-black px-3 py-2 text-sm text-white"
            value={draft.responseSpeed}
            onChange={(e) =>
              setDraft({
                ...draft,
                responseSpeed: e.target
                  .value as VoiceSessionPreferences["responseSpeed"],
              })
            }
          >
            <option value="fast">Rápida</option>
            <option value="balanced">Equilibrada</option>
            <option value="thoughtful">Reflexiva</option>
          </select>
        </label>
        <label className="block">
          <span className="ced-hud-text-muted text-xs">Paleta HUD</span>
          <select
            className="mt-1 w-full rounded border border-cyan-700/50 bg-black px-3 py-2 text-sm text-white"
            value={draft.palette}
            onChange={(e) =>
              setDraft({
                ...draft,
                palette: e.target.value as VoicePaletteId,
              })
            }
          >
            <option value="cyan">Cyan (default)</option>
            <option value="gold">Dorado</option>
            <option value="matrix">Matrix</option>
            <option value="iron">Iron Man</option>
          </select>
        </label>
      </div>
    </CedModal>
  );
}

export function CedHistoryPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [items, setItems] = useState<ConversationRow[]>([]);
  const [pdfs, setPdfs] = useState<PdfArtifact[]>([]);

  useEffect(() => {
    if (!open) return;
    void listConversations().then(setItems);
    void listSessionPdfs().then(setPdfs);
  }, [open]);

  if (!open) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-sm border-l border-cyan-500/40 bg-black shadow-2xl ced-panel-glow">
      <header className="flex items-center justify-between border-b border-cyan-500/30 px-4 py-3">
        <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-bold text-[#00e5ff]">
          HISTORIAL
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-[#888888] hover:text-white"
        >
          ✕
        </button>
      </header>
      <div className="max-h-[calc(100vh-3.5rem)] overflow-y-auto p-4">
        <section>
          <h3 className="ced-hud-text-muted mb-2 text-[10px] uppercase tracking-widest">
            PDFs de sesión
          </h3>
          <ul className="space-y-2 text-sm">
            {pdfs.length === 0 ? (
              <li className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-3 text-xs">
                Sin PDFs aún. Pide a CED: &quot;convierte esto a PDF&quot; por voz o chat.
              </li>
            ) : (
              pdfs.map((pdf) => (
                <li
                  key={pdf.file_id}
                  className="rounded border border-cyan-900/50 bg-[#0a0a0a] p-3"
                >
                  <p className="font-medium text-cyan-200">{pdf.title}</p>
                  <p className="ced-hud-text-muted mt-1 text-xs">
                    {pdf.created_at
                      ? new Date(pdf.created_at).toLocaleString("es-MX")
                      : "Reciente"}
                  </p>
                  <a
                    href={pdfDownloadUrl(pdf.file_id)}
                    download={pdf.filename}
                    className="mt-2 inline-flex text-xs font-semibold text-cyan-400 hover:text-cyan-200"
                  >
                    📄 Descargar PDF
                  </a>
                </li>
              ))
            )}
          </ul>
        </section>

        <section className="mt-6">
          <h3 className="ced-hud-text-muted mb-2 text-[10px] uppercase tracking-widest">
            Conversaciones
          </h3>
          <p className="ced-hud-text-muted text-xs">
            Guardadas en Supabase.
          </p>
          <ul className="mt-3 space-y-2 text-sm text-[#e0e0e0]">
            {items.length === 0 ? (
              <li className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-3">
                Sin conversaciones aún. Activa el asistente para empezar.
              </li>
            ) : (
              items.map((c) => (
                <li
                  key={c.id}
                  className="rounded border border-cyan-900/50 bg-[#0a0a0a] p-3"
                >
                  <p className="font-medium text-[#00e5ff]">{c.title}</p>
                  <p className="ced-hud-text-muted mt-1 text-xs">
                    {new Date(c.updated_at).toLocaleString("es-MX")}
                  </p>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>
    </aside>
  );
}
