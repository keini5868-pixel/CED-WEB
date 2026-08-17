import type { CarouselSnapshot } from "@/components/dashboard/carousel/types";

/** Datos mock Fase 3A — reemplazar por GET /v1/hud/carousel en 3B. */
export function getMockCarouselSnapshot(): CarouselSnapshot {
  return {
    updatedAt: new Date().toISOString(),
    cards: [
      {
        id: "news",
        kind: "news",
        title: "NEWS",
        accent: "cyan",
        badge: "📰",
        lines: [
          "IA generativa redefine flujos de venta B2B",
          "TechCrunch · hace 2 h",
        ],
        footer: "Conecta keywords en ajustes",
      },
      {
        id: "instagram",
        kind: "instagram",
        title: "INSTAGRAM",
        accent: "pink",
        badge: "📷",
        lines: ["12.4K seguidores", "+38 ayer · 4.2% engagement"],
        footer: "Conecta Instagram para datos reales",
      },
      {
        id: "leads",
        kind: "leads",
        title: "LEADS HOY",
        accent: "red",
        badge: "🎯",
        lines: ["7 leads detectados", "@maria_fit · score 92 · HOT"],
        footer: "Prospección activa al conectar CRM",
      },
      {
        id: "trending",
        kind: "trending",
        title: "TRENDING",
        accent: "orange",
        badge: "🔥",
        lines: [
          "1. #creatina  2. #jarvis  3. #automation",
          "Subiendo +18% esta semana",
        ],
      },
      {
        id: "activity",
        kind: "activity",
        title: "ACTIVIDAD CED",
        accent: "cyan",
        badge: "📊",
        lines: [
          "Voz: sesión 4 min",
          "Web brief: clavo industrial",
          "Tool: sistema avanzado OK",
        ],
      },
      {
        id: "business",
        kind: "business",
        title: "TU NEGOCIO",
        accent: "gold",
        badge: "📈",
        lines: ["3 conversiones esta semana", "Ingresos: demo · +12% vs anterior"],
        footer: "Stripe conectado en Fase 3C",
      },
      {
        id: "system",
        kind: "system",
        title: "SYSTEM",
        accent: "green",
        badge: "⚡",
        lines: [
          "API · OK",
          "Servicios internos OK",
        ],
        footer: "Health detallado en Fase 3B",
      },
    ],
  };
}
