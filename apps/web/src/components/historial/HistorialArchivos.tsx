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
      await downloadPdfBlob(row.file_id, row.filename || "documento-ced.pdf");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo descargar.");
    } finally {
      setBusyId(null);
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
                  <button
                    type="button"
                    onClick={() => void saveImage(row)}
                    disabled={busyId === row.id}
                    className="text-[10px] uppercase tracking-wider text-cyan-400 hover:text-cyan-200 disabled:opacity-50"
                  >
                    {busyId === row.id ? "Descargando…" : "Descargar"}
                  </button>
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
                className="flex items-center justify-between gap-3 rounded border border-cyan-900/50 bg-[#0a0a0a] p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-cyan-100">
                    {row.title || row.filename}
                  </p>
                  <p className="ced-hud-text-muted text-[10px]">
                    {formatWhen(row.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <a
                    href={pdfDownloadUrl(row.file_id)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[10px] uppercase tracking-wider text-cyan-400 hover:text-cyan-200"
                  >
                    Ver
                  </a>
                  <button
                    type="button"
                    onClick={() => void savePdf(row)}
                    disabled={busyId === row.file_id}
                    className="text-[10px] uppercase tracking-wider text-cyan-400 hover:text-cyan-200 disabled:opacity-50"
                  >
                    {busyId === row.file_id ? "…" : "Descargar"}
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
