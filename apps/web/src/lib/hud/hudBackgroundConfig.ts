/**
 * Tiempos HUD en background — voz primero, paneles/carrusel después.
 * No modificar sin validar que la voz sigue fluida.
 */
export const HUD_BACKGROUND = {
  /** Retraso antes de conectar SSE de paneles (deja respirar Gemini Live). */
  panelStreamConnectDelayMs: 8_000,
  /** Retraso antes de pedir datos al API de paneles tras una búsqueda por voz. */
  panelSearchDelayMs: 8_000,
  /** Carrusel CASTILLO — primera carga diferida. */
  carouselInitialDelayMs: 15_000,
  /** Carrusel — refresh de tarjetas (2 min). */
  carouselRefreshMs: 120_000,
} as const;

/** Retraso en servidor antes de Tavily/paneles (segundos). */
export const PANEL_SEARCH_SERVER_DELAY_SEC = 5;
