"use client";

import { useEffect, useState } from "react";

import { ImageLightbox } from "@/components/ui/ImageLightbox";
import {
  downloadPdfBlob,
  listSessionPdfs,
  pdfDownloadUrl,
  type PdfArtifact,
} from "@/lib/api/pdf";
import {
  downloadImageBlob,
  listGeneratedImages,
  type GeneratedImageRow,
} from "@/lib/api/media-history";
import { sendToTrash } from "@/lib/api/trash";
import { SelectToolbar, TrashIconButton } from "@/components/trash/TrashControls";

function formatWhen(value?: string): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("es-MX");
}

export function HistorialArchivos() {
  const [images, setImages] = useState<GeneratedImageRow[]>([]);
  const [pdfs, setPdfs] = useState<PdfArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<GeneratedImageRow | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busyTrash, setBusyTrash] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([listGeneratedImages(), listSessionPdfs()])
      .then(([imgs, docs]) => {
        if (cancelled) return;
        setImages(imgs);
        setPdfs(docs);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "No se pudo cargar el historial.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveImage(row: GeneratedImageRow) {
    setBusyId(row.id);
    try {
      const slug = (row.prompt || "imagen").slice(0, 40).replace(/\s+/g, "-");
      await downloadImageBlob(row.url, `${slug || "imagen-ced"}.png`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo descargar.");
    } finally {
      setBusyId(null);
    }
  }

  async function savePdf(row: PdfArtifact) {
    setBusyId(row.file_id);
    try {
      await downloadPdfBlob(row.file_id, row.filename || "documento-ced.pdf", {
        allowDuringVoice: true,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo descargar.");
    } finally {
      setBusyId(null);
    }
  }

  async function trashPicked() {
    const imageIds = images.filter((r) => picked.has(`image:${r.id}`)).map((r) => r.id);
    const pdfIds = pdfs.filter((r) => picked.has(`pdf:${r.file_id}`)).map((r) => r.file_id);
    setBusyTrash(true);
    try {
      if (imageIds.length) await sendToTrash("image", imageIds);
      if (pdfIds.length) await sendToTrash("pdf", pdfIds);
      setImages((prev) => prev.filter((r) => !imageIds.includes(r.id)));
      setPdfs((prev) => prev.filter((r) => !pdfIds.includes(r.file_id)));
      setPicked(new Set());
      setSelecting(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar a la papelera.");
    } finally {
      setBusyTrash(false);
    }
  }

  async function trashOne(scope: "image" | "pdf", id: string) {
    setBusyTrash(true);
    try {
      await sendToTrash(scope, [id]);
      if (scope === "image") setImages((prev) => prev.filter((r) => r.id !== id));
      else setPdfs((prev) => prev.filter((r) => r.file_id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar a la papelera.");
    } finally {
      setBusyTrash(false);
    }
  }

  if (loading) {
    return <p className="ced-hud-text-muted text-sm">Cargando archivos…</p>;
  }

  return (
    <div className="space-y-8">
      {error ? (
        <p className="rounded border border-red-500/40 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      <SelectToolbar
        selecting={selecting}
        selectedCount={picked.size}
        busy={busyTrash}
        onToggle={() => {
          setSelecting((v) => !v);
          setPicked(new Set());
        }}
        onTrash={() => void trashPicked()}
      />

      <section>
        <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wider text-cyan-300">
          IMÁGENES
        </h2>
        {images.length === 0 ? (
          <p className="ced-hud-text-muted mt-3 rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-sm">
            Aún no hay imágenes generadas. Pide a CED una foto o un creativo.
          </p>
        ) : (
          <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {images.map((row) => (
              <li
                key={row.id}
                className="overflow-hidden rounded border border-cyan-900/50 bg-[#0a0a0a]"
              >
                <button
                  type="button"
                  onClick={() => setLightbox(row)}
                  className="block w-full"
                  aria-label="Ver imagen"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={row.url}
                    alt={row.prompt || "Imagen generada"}
                    className="aspect-square w-full object-cover"
                  />
                </button>
                <div className="space-y-2 p-2">
                  <p className="line-clamp-2 text-[11px] text-cyan-200/90">
                    {row.prompt || "Imagen generada"}
                  </p>
                  <p className="ced-hud-text-muted text-[10px]">
                    {formatWhen(row.created_at)}
                  </p>
                <div className="flex items-center justify-between gap-1">
                  <button
                    type="button"
                    onClick={() => void saveImage(row)}
                    disabled={busyId === row.id}
                    className="text-[10px] uppercase tracking-wider text-cyan-400 hover:text-cyan-200 disabled:opacity-50"
                  >
                    {busyId === row.id ? "Descargando…" : "Descargar"}
                  </button>
                  {selecting ? (
                    <input
                      type="checkbox"
                      checked={picked.has(`image:${row.id}`)}
                      onChange={() => {
                        setPicked((prev) => {
                          const next = new Set(prev);
                          const key = `image:${row.id}`;
                          if (next.has(key)) next.delete(key);
                          else next.add(key);
                          return next;
                        });
                      }}
                    />
                  ) : (
                    <TrashIconButton
                      disabled={busyTrash}
                      onClick={() => void trashOne("image", row.id)}
                    />
                  )}
                </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wider text-cyan-300">
          PDF
        </h2>
        {pdfs.length === 0 ? (
          <p className="ced-hud-text-muted mt-3 rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-sm">
            Aún no hay PDFs. Pide a CED: «convierte esto a PDF».
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {pdfs.map((row) => (
              <li
                key={row.file_id}
                className="flex flex-col gap-2 rounded border border-cyan-900/50 bg-[#0a0a0a] p-3"
              >
                <div className="flex min-w-0 items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-sm text-cyan-100">
                      {row.title || row.filename}
                    </p>
                    <p className="ced-hud-text-muted text-[10px]">
                      {formatWhen(row.created_at)}
                    </p>
                  </div>
                  {selecting ? (
                    <input
                      type="checkbox"
                      className="mt-1 h-5 w-5 shrink-0"
                      checked={picked.has(`pdf:${row.file_id}`)}
                      onChange={() => {
                        setPicked((prev) => {
                          const next = new Set(prev);
                          const key = `pdf:${row.file_id}`;
                          if (next.has(key)) next.delete(key);
                          else next.add(key);
                          return next;
                        });
                      }}
                    />
                  ) : (
                    <TrashIconButton
                      disabled={busyTrash}
                      onClick={() => void trashOne("pdf", row.file_id)}
                    />
                  )}
                </div>
                <div className="flex w-full min-w-0 gap-2">
                  <a
                    href={pdfDownloadUrl(row.file_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex min-h-11 flex-1 items-center justify-center rounded border border-cyan-700/50 px-3 text-[11px] font-semibold uppercase tracking-wider text-cyan-300"
                  >
                    Abrir
                  </a>
                  <button
                    type="button"
                    onClick={() => void savePdf(row)}
                    disabled={busyId === row.file_id}
                    className="inline-flex min-h-11 flex-1 items-center justify-center rounded border border-cyan-400/60 bg-cyan-400/10 px-3 text-[11px] font-semibold uppercase tracking-wider text-cyan-200 disabled:opacity-50"
                  >
                    {busyId === row.file_id ? "Descargando…" : "Descargar"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ImageLightbox
        src={lightbox?.url ?? ""}
        alt={lightbox?.prompt || "Imagen generada"}
        open={Boolean(lightbox)}
        onClose={() => setLightbox(null)}
      />
    </div>
  );
}
