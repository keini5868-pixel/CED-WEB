"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { CedButton, CedModal } from "@ced/ui";
import type { VoicePaletteId, VoiceSessionPreferences } from "@ced/types";

import {
  listConversations,
  type ConversationRow,
} from "@/lib/api/conversations";
import { downloadPdfBlob, listSessionPdfs, type PdfArtifact } from "@/lib/api/pdf";
import {
  downloadImageBlob,
  listGeneratedImages,
  type GeneratedImageRow,
} from "@/lib/api/media-history";
import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { OPENAI_VOICE_OPTIONS } from "@/lib/voice/openaiVoices";
import {
  JARVIS_VOICE_PRESET,
  STANDARD_VOICE_PRESET,
  isJarvisPreset,
} from "@/lib/voice/voicePresets";
import { fetchUserAddress, updateUserAddress } from "@/lib/api/profile";
import { clearEphemeralTokenCache } from "@/lib/voice/ephemeralTokenCache";
import type { UserGender } from "@/lib/voice/addressPreferenceIntent";
import { ThemeAppearanceToggle } from "@/components/account/ThemeAppearanceToggle";
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
      title="CONFIGURACIÓN"
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
      <div className="max-h-[min(62vh,520px)] space-y-4 overflow-y-auto overscroll-y-contain pr-1 [-webkit-overflow-scrolling:touch]">
        <ThemeAppearanceToggle />
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
              Tono formal · pausado · ejecutivo
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
            <div className="font-semibold tracking-wide text-amber-200">Voz Jarvis</div>
            <p className="mt-1 text-[11px] leading-relaxed opacity-90">
              Tono grave y pausado configurado en servidor. Hable claro, cerca del micrófono.
            </p>
          </div>
        ) : (
        <div>
          <span className="ced-hud-text-muted text-xs">
            Voz conversacional (requiere reiniciar sesión)
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

type HistoryTab = "chats" | "pdfs" | "images";

function compactPdfName(pdf: PdfArtifact): string {
  const filename = (pdf.filename || "").trim();
  if (filename && !/^documento-ced\.pdf$/i.test(filename)) {
    return filename;
  }
  const title = (pdf.title || "").replace(/\s+/g, " ").trim();
  const first = (title.split(/[.!?\n]/)[0] || title).trim();
  if (first.length > 0 && first.length <= 64) {
    return first.toLowerCase().endsWith(".pdf") ? first : `${first}.pdf`;
  }
  if (first.length > 64) {
    return `${first.slice(0, 52).trim()}….pdf`;
  }
  return filename || "documento-ced.pdf";
}

export function CedHistoryPanel({
  open,
  onClose,
  onResume,
  onNewChat,
  activeConversationId,
}: {
  open: boolean;
  onClose: () => void;
  onResume?: (conversationId: string) => void;
  onNewChat?: () => void;
  activeConversationId?: string | null;
}) {
  const [tab, setTab] = useState<HistoryTab>("chats");
  const [items, setItems] = useState<ConversationRow[]>([]);
  const [pdfs, setPdfs] = useState<PdfArtifact[]>([]);
  const [images, setImages] = useState<GeneratedImageRow[]>([]);
  const [lightbox, setLightbox] = useState<GeneratedImageRow | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    setTab("chats");
    void listConversations()
      .then(setItems)
      .catch(() => setItems([]));
    void listSessionPdfs()
      .then(setPdfs)
      .catch(() => setPdfs([]));
    void listGeneratedImages()
      .then(setImages)
      .catch(() => setImages([]));
  }, [open]);

  if (!open || !mounted) return null;
  return createPortal(
    <>
      <button
        type="button"
        className="fixed inset-0 z-[200] bg-black/50"
        aria-label="Cerrar historial"
        onClick={onClose}
      />
      <aside className="ced-panel-glow fixed inset-y-0 left-0 z-[201] flex w-full max-w-sm flex-col border-r border-cyan-500/40 bg-black pl-[env(safe-area-inset-left,0px)] shadow-2xl sm:left-0">
      <header className="flex shrink-0 items-center justify-between border-b border-cyan-500/30 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
        <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-bold text-[var(--ced-cyan)]">
          CHATS
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar historial"
          className="-mr-1 flex h-11 min-w-11 items-center justify-center rounded text-lg text-[#888888] hover:bg-cyan-950/40 hover:text-white"
        >
          ✕
        </button>
      </header>
      <nav className="flex shrink-0 border-b border-cyan-900/50 px-2" aria-label="Secciones">
        {(
          [
            ["chats", "Chats"],
            ["pdfs", "PDFs"],
            ["images", "Imágenes"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-selected={tab === id}
            className={`flex-1 px-2 py-2.5 text-[11px] font-semibold uppercase tracking-wide ${
              tab === id
                ? "border-b-2 border-cyan-400 text-cyan-200"
                : "text-[#888888] hover:text-cyan-200"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {tab === "chats" ? (
          <>
            {onNewChat ? (
              <CedButton
                className="mb-4 w-full"
                onClick={() => {
                  onNewChat();
                  onClose();
                }}
              >
                Nuevo chat
              </CedButton>
            ) : null}
            <p className="ced-hud-text-muted mb-3 text-xs">
              Toca un hilo para seguir en el mismo tema.
            </p>
            <ul className="space-y-2 text-sm text-[#e0e0e0]">
              {items.length === 0 ? (
                <li className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-3">
                  Sin conversaciones aún. Escribe o habla con CED para empezar.
                </li>
              ) : (
                items.map((c) => {
                  const active = activeConversationId === c.id;
                  return (
                    <li
                      key={c.id}
                      className={`rounded border bg-[#0a0a0a] p-3 ${
                        active ? "border-cyan-400/70" : "border-cyan-900/50"
                      }`}
                    >
                      <button
                        type="button"
                        className="w-full text-left"
                        onClick={() => {
                          if (onResume) {
                            onResume(c.id);
                            onClose();
                          }
                        }}
                      >
                        <p className="font-medium text-[var(--ced-cyan)]">{c.title}</p>
                        {c.preview ? (
                          <p className="ced-hud-text-muted mt-1 line-clamp-2 text-xs">
                            {c.preview}
                          </p>
                        ) : null}
                        <p className="ced-hud-text-muted mt-1 text-xs">
                          {c.channel === "voice" ? "Voz" : "Texto"} ·{" "}
                          {new Date(c.updated_at).toLocaleString("es-MX")}
                        </p>
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </>
        ) : null}

        {tab === "pdfs" ? (
          <ul className="space-y-2">
            {pdfs.length === 0 ? (
              <li className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-3 text-xs">
                Sin PDFs aún. Pide a CED: &quot;convierte esto a PDF&quot; por voz o chat.
              </li>
            ) : (
              pdfs.map((pdf) => (
                <li
                  key={pdf.file_id}
                  className="flex items-center gap-3 rounded border border-cyan-900/50 bg-[#0a0a0a] p-3"
                >
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-cyan-950/80 text-lg"
                    aria-hidden
                  >
                    📄
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-cyan-100">
                      {compactPdfName(pdf)}
                    </p>
                    <p className="ced-hud-text-muted text-[11px]">
                      {pdf.created_at
                        ? new Date(pdf.created_at).toLocaleString("es-MX")
                        : "Reciente"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      void downloadPdfBlob(pdf.file_id, pdf.filename || compactPdfName(pdf), {
                        allowDuringVoice: true,
                      }).catch((e) =>
                        alert(
                          e instanceof Error
                            ? e.message
                            : "No se pudo descargar el PDF.",
                        ),
                      )
                    }
                    className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-cyan-400 hover:text-cyan-200"
                  >
                    Descargar
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}

        {tab === "images" ? (
          images.length === 0 ? (
            <p className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-3 text-xs">
              Sin imágenes aún. Pide a CED una foto o un creativo.
            </p>
          ) : (
            <ul className="grid grid-cols-2 gap-2">
              {images
                .filter((row) => Boolean(row.url))
                .map((row) => (
                <li
                  key={row.id}
                  className="overflow-hidden rounded border border-cyan-900/50 bg-[#0a0a0a]"
                >
                  <button
                    type="button"
                    onClick={() => setLightbox(row)}
                    className="block w-full bg-black"
                    aria-label="Ver imagen"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={row.url}
                      alt=""
                      className="aspect-square w-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  </button>
                  <button
                    type="button"
                    disabled={busyId === row.id}
                    onClick={() => {
                      setBusyId(row.id);
                      void downloadImageBlob(row.url, "imagen-ced.png")
                        .catch((e) =>
                          alert(
                            e instanceof Error
                              ? e.message
                              : "No se pudo descargar.",
                          ),
                        )
                        .finally(() => setBusyId(null));
                    }}
                    className="w-full py-2 text-[10px] font-semibold uppercase tracking-wide text-cyan-400 hover:bg-cyan-950/50 hover:text-cyan-200 disabled:opacity-50"
                  >
                    {busyId === row.id ? "…" : "Descargar"}
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </div>
    </aside>
      <ImageLightbox
        src={lightbox?.url ?? ""}
        alt="Imagen"
        open={Boolean(lightbox)}
        onClose={() => setLightbox(null)}
      />
    </>,
    document.body,
  );
}
