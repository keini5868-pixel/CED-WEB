"use client";

import { useEffect } from "react";

import { useHudFeed } from "@/contexts/HudFeedContext";

const INTEL_LINES: { kind: "news" | "stat" | "report"; text: string }[] = [
  {
    kind: "news",
    text: "Tendencia: contenido corto en Reels sigue dominando alcance orgánico en LATAM.",
  },
  {
    kind: "stat",
    text: "Métrica: +23% engagement promedio en publicaciones con CTA claro (últimos 7 días).",
  },
  {
    kind: "report",
    text: "Informe: prospección activa — revisa leads en panel HIST cuando finalices la sesión.",
  },
  {
    kind: "news",
    text: "Noticia: Meta amplía herramientas de automatización para pymes en Ads Manager.",
  },
  {
    kind: "stat",
    text: "Estadística: horario pico de respuesta en DM — 18:00 a 21:00 (zona local).",
  },
  {
    kind: "report",
    text: "Brief: prioriza 3 nichos con mayor intención de compra detectada esta semana.",
  },
  {
    kind: "news",
    text: "Actualización: búsqueda por voz en comercio digital crece 19% interanual.",
  },
  {
    kind: "stat",
    text: "KPI sugerido: tasa de respuesta < 2 h mejora conversión en funnels B2C.",
  },
];

/** Inyecta noticias / estadísticas / informes simulados en el ticker DRONES. */
export function useHudIntelStream(enabled = true) {
  const { pushLine } = useHudFeed();

  useEffect(() => {
    if (!enabled) return;
    let index = 0;
    const tick = () => {
      const line = INTEL_LINES[index % INTEL_LINES.length]!;
      index += 1;
      pushLine(line.text, line.kind);
    };
    tick();
    const id = setInterval(tick, 14_000);
    return () => clearInterval(id);
  }, [enabled, pushLine]);
}
