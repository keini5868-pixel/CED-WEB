"use client";

import { useEffect, useState } from "react";

import { CedButton, CedModal } from "@ced/ui";
import type { VoicePaletteId, VoiceSessionPreferences } from "@ced/types";

import {
  getConversationMessages,
  listConversations,
  type ConversationRow,
} from "@/lib/api/conversations";
import { downloadPdfBlob, listSessionPdfs, type PdfArtifact } from "@/lib/api/pdf";
import { OPENAI_VOICE_OPTIONS } from "@/lib/voice/openaiVoices";
import {
  JARVIS_VOICE_PRESET,
  STANDARD_VOICE_PRESET,
  isJarvisPreset,
} from "@/lib/voice/voicePresets";
import { fetchUserAddress, updateUserAddress } from "@/lib/api/profile";
import { clearEphemeralTokenCache } from "@/lib/voice/ephemeralTokenCache";
import type { UserGender } from "@/lib/voice/addressPreferenceIntent";
import { isRetellVoice } from "@/lib/voice/voiceProvider";

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
        <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row sm:gap-3">
          <CedButton variant="ghost" onClick={onClose} className="w-full sm:w-auto">
            CANCELAR
          </CedButton>
          <CedButton variant="danger" onClick={onConfirm} className="w-full sm:w-auto">
            DETENER
          </CedButton>
        </div>
      }
    >
      <p className="ced-hud-text-body">
        ¿Cerrar la sesión de voz CED? Perderás el contexto de voz actual.
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
  const [addressDraft, setAddressDraft] = useState({
    preferredAddress: "",
    gender: "" as UserGender | "",
  });
  const [addressPreview, setAddressPreview] = useState("");

  useEffect(() => {
    if (open) setDraft(prefs);
  }, [open, prefs]);

  useEffect(() => {
    if (!open) return;
    void fetchUserAddress().then((a) => {
      if (!a) return;
      setAddressDraft({
        preferredAddress: a.preferredAddress || a.honorific || "",
        gender: a.gender || "",
      });
      setAddressPreview(a.displayName);
    });
  }, [open]);

  const voiceChanged = draft.voiceName !== prefs.voiceName;
  const retellMode = isRetellVoice();

  return (
    <CedModal
      open={open}
      onClose={onClose}
      title="CONFIGURACIÓN DE VOZ"
      footer={
        <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row sm:gap-3">
          <CedButton variant="ghost" onClick={onClose} className="w-full sm:w-auto">
            CERRAR
          </CedButton>
          <CedButton
            className="w-full sm:w-auto"
            onClick={() => {
              void (async () => {
                onSave(draft);
                const updated = await updateUserAddress({
                  preferredAddress: addressDraft.preferredAddress,
                  gender: addressDraft.gender || null,
                });
                if (updated) {
                  setAddressPreview(updated.displayName);
                  clearEphemeralTokenCache();
                }
                onClose();
              })();
            }}
          >
            GUARDAR CONFIGURACIÓN
          </CedButton>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setDraft({ ...JARVIS_VOICE_PRESET, palette: draft.palette })}
            className={`rounded border px-3 py-2.5 text-left text-xs transition-colors ${
              isJarvisPreset(draft)
                ? "border-amber-400/70 bg-amber-950/30 text-amber-100"
                : "border-cyan-900/50 bg-black text-zinc-400 hover:border-cyan-700"
            }`}
          >
            <div className="font-semibold tracking-wide">Modo Jarvis</div>
            <div className="mt-0.5 text-[10px] opacity-80">
              {retellMode
                ? "Retell · tono formal · pausado · ejecutivo"
                : "Echo · formal · pausado · ejecutivo"}
            </div>
          </button>
          <button
            type="button"
            onClick={() => setDraft({ ...STANDARD_VOICE_PRESET, palette: draft.palette })}
            className={`rounded border px-3 py-2.5 text-left text-xs transition-colors ${
              draft.voiceProfile === "standard"
                ? "border-cyan-400 bg-cyan-950/40 text-cyan-200"
                : "border-cyan-900/50 bg-black text-zinc-400 hover:border-cyan-700"
            }`}
          >
            <div className="font-semibold tracking-wide">Estándar</div>
            <div className="mt-0.5 text-[10px] opacity-80">
              Alloy · conversacional · ágil
            </div>
          </button>
        </div>

        {retellMode ? (
          <div className="rounded border border-amber-500/30 bg-amber-950/20 px-3 py-3 text-xs text-amber-100/90">
            <div className="font-semibold tracking-wide text-amber-200">Voz Retell (Jarvis)</div>
            <p className="mt-1 text-[11px] leading-relaxed opacity-90">
              CED usa su clon Jarvis en Retell + Cartesia. Tono grave y pausado configurado en
              servidor. Para cambiar la voz, actualice el agente en Retell dashboard y ejecute
              bootstrap.
            </p>
            <p className="mt-2 text-[10px] text-zinc-400">
              El reconocimiento de voz usa modo preciso (español). Hable claro, cerca del micrófono.
            </p>
          </div>
        ) : (
        <div>
          <span className="ced-hud-text-muted text-xs">
            Voz OpenAI Realtime (requiere reiniciar sesión)
          </span>
          <p className="ced-hud-text-muted mt-1 text-[10px]">
            Activa: <strong className="text-cyan-400">{prefs.voiceName}</strong>
            {micOn
              ? " · Pulsa APLICAR VOZ para oír el cambio"
              : " · Se aplicará al activar MIC"}
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {OPENAI_VOICE_OPTIONS.map((voice) => (
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
                <div className="flex items-center gap-1.5 font-medium">
                  {voice.name}
                  {voice.badge ? (
                    <span className="rounded bg-amber-500/20 px-1 py-0.5 text-[9px] font-bold tracking-wide text-amber-300">
                      {voice.badge}
                    </span>
                  ) : null}
                </div>
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
        )}

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

        <div className="space-y-3 rounded border border-cyan-900/40 bg-black/40 p-3">
          <p className="ced-hud-text-muted text-xs font-medium uppercase tracking-wider">
            Cómo te llama CED
          </p>
          <p className="ced-hud-text-muted text-[10px]">
            El saludo usa tu género o el título que elijas (Señor, Señora, Jefe, tu nombre).
            También puedes decirlo por voz: &quot;llámame señor&quot;.
          </p>
          <label className="block">
            <span className="ced-hud-text-muted text-xs">Tratamiento preferido</span>
            <input
              type="text"
              className="mt-1 w-full rounded border border-cyan-700/50 bg-black px-3 py-2 text-sm text-white"
              placeholder="Ej: Señor, Señora, Keini, Jefe"
              value={addressDraft.preferredAddress}
              onChange={(e) =>
                setAddressDraft((d) => ({ ...d, preferredAddress: e.target.value }))
              }
            />
          </label>
          <label className="block">
            <span className="ced-hud-text-muted text-xs">Género (título por defecto)</span>
            <select
              className="mt-1 w-full rounded border border-cyan-700/50 bg-black px-3 py-2 text-sm text-white"
              value={addressDraft.gender}
              onChange={(e) =>
                setAddressDraft((d) => ({
                  ...d,
                  gender: e.target.value as UserGender | "",
                }))
              }
            >
              <option value="">Sin preferencia</option>
              <option value="male">Masculino → Señor</option>
              <option value="female">Femenino → Señora</option>
              <option value="neutral">Neutral → solo nombre</option>
            </select>
          </label>
          {addressPreview ? (
            <p className="ced-hud-text-muted text-[10px]">
              Vista previa saludo: <span className="text-cyan-300">{addressPreview}</span>
            </p>
          ) : null}
        </div>

        <div className="space-y-3 rounded border border-cyan-900/40 bg-black/40 p-3">
          <p className="ced-hud-text-muted text-xs font-medium uppercase tracking-wider">
            Ajuste fino de voz
          </p>
          <p className="ced-hud-text-muted text-[10px]">
            OpenAI no permite cambiar tono en tiempo real como un ecualizador; estos controles
            guían el estilo de CED en la próxima sesión (ritmo, calidez y expresividad).
          </p>
          <label className="block">
            <span className="ced-hud-text-muted flex justify-between text-xs">
              <span>Ritmo</span>
              <span>{draft.voicePace}%</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={draft.voicePace}
              onChange={(e) =>
                setDraft((d) => ({ ...d, voicePace: Number(e.target.value) }))
              }
              className="mt-1 w-full accent-cyan-400"
            />
            <span className="ced-hud-text-muted flex justify-between text-[10px]">
              <span>Pausado</span>
              <span>Ágil</span>
            </span>
          </label>
          <label className="block">
            <span className="ced-hud-text-muted flex justify-between text-xs">
              <span>Calidez</span>
              <span>{draft.voiceWarmth}%</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={draft.voiceWarmth}
              onChange={(e) =>
                setDraft((d) => ({ ...d, voiceWarmth: Number(e.target.value) }))
              }
              className="mt-1 w-full accent-cyan-400"
            />
            <span className="ced-hud-text-muted flex justify-between text-[10px]">
              <span>Formal</span>
              <span>Cálido</span>
            </span>
          </label>
          <label className="block">
            <span className="ced-hud-text-muted flex justify-between text-xs">
              <span>Expresividad</span>
              <span>{draft.voiceEnergy}%</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={draft.voiceEnergy}
              onChange={(e) =>
                setDraft((d) => ({ ...d, voiceEnergy: Number(e.target.value) }))
              }
              className="mt-1 w-full accent-cyan-400"
            />
            <span className="ced-hud-text-muted flex justify-between text-[10px]">
              <span>Calma</span>
              <span>Energía</span>
            </span>
          </label>
        </div>

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

        <p className="ced-hud-text-muted pb-2 text-center text-[10px]">
          Desliza hacia arriba para ver todas las opciones
        </p>
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
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedMessages, setExpandedMessages] = useState<
    { role: string; content: string; created_at?: string }[]
  >([]);

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
                  <button
                    type="button"
                    onClick={() =>
                      void downloadPdfBlob(pdf.file_id, pdf.filename).catch((e) =>
                        alert(
                          e instanceof Error
                            ? e.message
                            : "No se pudo descargar el PDF.",
                        ),
                      )
                    }
                    className="mt-2 inline-flex text-xs font-semibold text-cyan-400 hover:text-cyan-200"
                  >
                    📄 Descargar PDF
                  </button>
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
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => {
                      if (expandedId === c.id) {
                        setExpandedId(null);
                        setExpandedMessages([]);
                        return;
                      }
                      setExpandedId(c.id);
                      void getConversationMessages(c.id)
                        .then((data) => setExpandedMessages(data.messages))
                        .catch(() => setExpandedMessages([]));
                    }}
                  >
                    <p className="font-medium text-[#00e5ff]">{c.title}</p>
                    {c.preview ? (
                      <p className="ced-hud-text-muted mt-1 line-clamp-2 text-xs">{c.preview}</p>
                    ) : null}
                    <p className="ced-hud-text-muted mt-1 text-xs">
                      {new Date(c.updated_at).toLocaleString("es-MX")}
                    </p>
                  </button>
                  {expandedId === c.id && expandedMessages.length > 0 ? (
                    <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto border-t border-cyan-900/40 pt-3 text-xs">
                      {expandedMessages.map((m) => (
                        <li key={`${m.created_at}-${m.content.slice(0, 20)}`}>
                          <span className="text-cyan-600">
                            {m.role === "user" ? "Tú" : "CED"}:
                          </span>{" "}
                          {m.content}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </section>
      </div>
    </aside>
  );
}
