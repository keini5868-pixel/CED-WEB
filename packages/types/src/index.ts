/** Planes de suscripción CED */
export type SubscriptionPlanId =
  | "cierre"
  | "starter"
  | "pro"
  | "elite"
  | "founding"
  | "free_basic"
  | "elite_founding"
  | "elite_regular";

export type UserRole = "client" | "super_admin";

export interface PlanFeatures {
  geminiMinutesPerDay: number;
  webSearchesPerDay: number;
  aiImagesPerDay: number;
  voiceEnabled: boolean;
  cameraEnabled: boolean;
  metaSocialEnabled: boolean;
  prospectionEnabled: boolean;
}

export const FOUNDING_MEMBER_MAX_SLOTS = 50;
export const TRIAL_DAYS = 7;
/** Minutos de voz/día durante el trial (mismo cupo diario que los planes). */
export const TRIAL_VOICE_MINUTES_PER_DAY = 20;

export const PLAN_PRICES_USD: Record<
  "cierre" | "starter" | "pro" | "elite" | "founding",
  number
> = {
  cierre: 20,
  starter: 30,
  pro: 59,
  elite: 99,
  founding: 149,
};

export const RECHARGE_MARGIN_KEINI = 0.4;
export const RECHARGE_CLIENT_SHARE = 0.6;
/** $0.10/min voz — alineado con API (monedero multi-recurso). */
export const VOICE_COST_PER_MIN_USD = 0.1;
export const IMAGE_STD_COST_USD = 0.02;
export const IMAGE_HD_COST_USD = 0.04;
export const WEB_SEARCH_COST_USD = 0.01;
export const PDF_COST_USD = 0.05;
/** @deprecated usar VOICE_COST_PER_MIN_USD * 60 */
export const GEMINI_COST_PER_HOUR_USD = VOICE_COST_PER_MIN_USD * 60;
export const RECHARGE_MIN_USD = 10;
export const RECHARGE_MAX_USD = 500;
export const RECHARGE_QUICK_AMOUNTS_USD = [10, 20, 40, 50, 100] as const;

/** Capacidades incluidas en todos los planes (sin costo variable de uso). */
export const PLAN_INCLUDED_ALWAYS = [
  "YouTube",
  "Memoria conversacional",
] as const;

export interface RechargeQuote {
  amountPaidUsd: number;
  clientBalanceUsd: number;
  estimatedExtraHours: number;
  estimatedVoiceMinutes: number;
  estimatedImagesStd: number;
  estimatedWebSearches: number;
  estimatedPdfs: number;
  marginKeiniUsd: number;
  neverExpires: true;
}

export function quoteRecharge(amountUsd: number): RechargeQuote {
  const paid = Math.max(RECHARGE_MIN_USD, Math.min(RECHARGE_MAX_USD, amountUsd));
  const clientBalanceUsd = paid * RECHARGE_CLIENT_SHARE;
  const marginKeiniUsd = paid * RECHARGE_MARGIN_KEINI;
  const estimatedVoiceMinutes =
    VOICE_COST_PER_MIN_USD > 0 ? clientBalanceUsd / VOICE_COST_PER_MIN_USD : 0;
  const estimatedExtraHours = estimatedVoiceMinutes / 60;
  return {
    amountPaidUsd: paid,
    clientBalanceUsd: Math.round(clientBalanceUsd * 100) / 100,
    estimatedExtraHours: Math.round(estimatedExtraHours * 100) / 100,
    estimatedVoiceMinutes: Math.floor(estimatedVoiceMinutes),
    estimatedImagesStd: Math.floor(
      IMAGE_STD_COST_USD > 0 ? clientBalanceUsd / IMAGE_STD_COST_USD : 0,
    ),
    estimatedWebSearches: Math.floor(
      WEB_SEARCH_COST_USD > 0 ? clientBalanceUsd / WEB_SEARCH_COST_USD : 0,
    ),
    estimatedPdfs: Math.floor(PDF_COST_USD > 0 ? clientBalanceUsd / PDF_COST_USD : 0),
    marginKeiniUsd: Math.round(marginKeiniUsd * 100) / 100,
    neverExpires: true,
  };
}

const COMMON_FREE_TOOLS = [
  "YouTube",
  "Memoria conversacional",
] as const;

/**
 * Progresión acumulativa — cada plan incluye todo lo del anterior + lo nuevo.
 * Regla: NUNCA poner cantidades de minutos de voz aquí. Los cupos de voz
 * viven solo en `apps/api/app/domain/plans.py` (kill-switch interno) y NO
 * se muestran en home, /pricing ni tarjetas de planes.
 *
 * Regla: cada `highlights` lista TODAS las herramientas del plan de forma
 * explícita y completa (acumulativo) — NUNCA usar un atajo tipo "Todo
 * Starter +" / "Todo Pro +". Cada tarjeta debe ser autosuficiente, sin
 * obligar a mirar el plan anterior para saber qué incluye.
 *
 * Tanto la home (`/`) como `/pricing` renderizan el arreglo `highlights`
 * COMPLETO, sin recortar (nunca usar `.slice()` sobre esto — un recorte
 * parcial rompe la regla de listado explícito, sobre todo en Founding, cuyo
 * valor está justamente en mostrarlo todo). El orden solo importa para
 * legibilidad: primero las capacidades NUEVAS de ese nivel, al final las
 * heredadas de niveles previos.
 */
export const PUBLIC_PLANS = [
  {
    id: "free_basic" as const,
    label: "CED Básico",
    priceUsd: 0,
    highlights: [
      "Creación de imágenes",
      "Creación de PDF",
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
    ],
  },
  {
    id: "cierre" as const,
    label: "CED PM International",
    priceUsd: 22,
    highlights: [
      "Cerrador de clientes PM International / FitLine",
      "Asistente de voz Jarvis",
      "Conocimiento de productos y objeciones",
      "Prospección y redes sociales",
      "Búsquedas web",
      "Chat de texto",
    ],
  },
  {
    id: "starter" as const,
    label: "CED Starter",
    priceUsd: 30,
    highlights: [
      "Asistente de voz CED",
      "Búsquedas web (15/día)",
      "Creación de imágenes",
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
    ],
  },
  {
    id: "pro" as const,
    label: "CED Pro",
    priceUsd: 59,
    highlights: [
      "Cámara por voz (análisis de imagen)",
      "Búsquedas web ilimitadas",
      "Creación de PDF",
      "Publicación en redes sociales (Facebook / Instagram)",
      "Asistente de voz CED",
      "Creación de imágenes",
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
    ],
  },
  {
    id: "elite" as const,
    label: "CED Élite",
    priceUsd: 99,
    highlights: [
      "Modo avanzado (análisis profundo con Claude)",
      "Modo de prospección",
      "Mapa y navegación",
      "Publicación en redes sociales (Facebook / Instagram)",
      "Cámara por voz (análisis de imagen)",
      "Búsquedas web ilimitadas",
      "Creación de PDF",
      "Asistente de voz CED",
      "Creación de imágenes",
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
    ],
  },
  {
    id: "founding" as const,
    label: "CED Founding",
    priceUsd: 149,
    highlights: [
      "Precio bloqueado por 6 meses",
      "Cupos limitados",
      "Modo avanzado (análisis profundo con Claude)",
      "Modo de prospección",
      "Mapa y navegación",
      "Publicación en redes sociales (Facebook / Instagram)",
      "Cámara por voz (análisis de imagen)",
      "Búsquedas web ilimitadas",
      "Creación de PDF",
      "Asistente de voz CED",
      "Creación de imágenes",
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
    ],
  },
] as const;

/** Estados del orbe central JARVIS (Fase 2) */
export type OrbState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "error"
  | "paused";

export const ORB_STATE_LABELS: Record<OrbState, string> = {
  idle: "Listo cuando quieras",
  listening: "Escuchándote… (habla o interrumpe)",
  processing: "Procesando...",
  speaking: "Hablando...",
  error: "Error — intenta de nuevo",
  paused: "En pausa",
};

export type VoicePaletteId = "cyan" | "gold" | "matrix" | "iron";

export type GeminiVoiceId = string;

export type VoiceProfileId = "standard" | "jarvis" | "fitline";

export interface VoiceSessionPreferences {
  language: "es" | "en" | "pt";
  responseSpeed: "fast" | "balanced" | "thoughtful";
  voiceName: GeminiVoiceId;
  palette: VoicePaletteId;
  /** 0 = más lento/pausado, 100 = más ágil */
  voicePace: number;
  /** 0 = más formal, 100 = más cálido/cercano */
  voiceWarmth: number;
  /** 0 = más calmada, 100 = más expresiva/energética */
  voiceEnergy: number;
  /** Perfil de personalidad oral (prompt backend) */
  voiceProfile: VoiceProfileId;
}

export const DEFAULT_VOICE_PREFERENCES: VoiceSessionPreferences = {
  language: "es",
  responseSpeed: "balanced",
  voiceName: "echo",
  palette: "cyan",
  voicePace: 35,
  voiceWarmth: 30,
  voiceEnergy: 32,
  voiceProfile: "jarvis",
};

export type HudPanelId = "city" | "global" | "drones" | "waves" | "summary";
export type HudState = "idle" | "searching" | "receiving" | "complete";

export type PanelEvent =
  | { type: "search_started"; query: string }
  | { type: "state"; hud: HudState }
  | {
      type: "panel_item";
      panel: HudPanelId;
      payload: Record<string, unknown>;
    }
  | { type: "summary_chunk"; text: string }
  | { type: "search_complete" };

export interface UsageBalance {
  planMinutesDaily: number;
  usedMinutesToday: number;
  rechargeBalanceUsd: number;
  bonusMinutesFromBalance: number;
  totalAvailableMinutes: number;
  warningAtPercent: number;
  blocked: boolean;
  needsRecharge?: boolean;
  planId?: SubscriptionPlanId;
  subscriptionStatus?: string;
  trialEndsAt?: string | null;
  isFoundingMember: boolean;
  priceLockedForLife: boolean;
  /** gemini = FitLine/Cierre (sin Jarvis); retell = premium Jarvis */
  voiceStack?: "gemini" | "retell" | string;
  /** openai | retell — transporte real de audio */
  voiceTransport?: "openai" | "retell" | string;
}
