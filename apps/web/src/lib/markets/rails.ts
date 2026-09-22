/**
 * Spec de mercados CED — cimientos, sin UI ni API Kraken.
 * Tras AKINDO: cajón overlay Mesa | Midnight (mismo patrón que Chats).
 */

export const MARKETS_SHIP_AFTER = "akindo-wave-2";

export const MARKETS_HUD = {
  control: "status-bar-or-sistema",
  pattern: "overlay-drawer",
  tabs: ["mesa", "midnight"] as const,
  alongside: "Chats",
} as const;

/** Kraken lista NIGHT en red Cardano — no otra chain. */
export const NIGHT_KRAKEN_NETWORK = "cardano";

export const MESA_COPY =
  "Operas en Kraken. Cuenta identificada (KYC). Esto no es privado ni es CED Shield.";

export const MIDNIGHT_COPY =
  "Esto corre en Midnight. Privacidad por prueba ZK (hash/sello), no por el libro del exchange.";

export const BRIDGE_COPY =
  "Comprar NIGHT en Mesa (Kraken, red Cardano) → retirar a tu wallet → Lace / Midnight. Tres pasos. No es un solo botón.";

export type MesaPair = {
  base: string;
  quote: string;
  krakenAlt?: string;
  note?: string;
};

/** Núcleo v1 — no el catálogo entero de Kraken. Filtrar siempre por país. */
export const MESA_CORE_PAIRS: readonly MesaPair[] = [
  { base: "BTC", quote: "USD", krakenAlt: "XBT" },
  { base: "ETH", quote: "USD" },
  { base: "SOL", quote: "USD" },
  { base: "ADA", quote: "USD" },
  { base: "USDC", quote: "USD" },
  { base: "USDT", quote: "USD" },
  { base: "NIGHT", quote: "USD", note: "puente a Midnight; funding en Cardano" },
  { base: "XRP", quote: "USD" },
  { base: "LINK", quote: "USD" },
  { base: "AVAX", quote: "USD" },
];

export const MESA_V1_EXCLUDE = [
  "memecoins de cola",
  "margin",
  "futures",
  "xStocks",
  "leverage",
  "tickers sin withdraw claro en esa región",
] as const;

export const MIDNIGHT_SCOPE = [
  "NIGHT",
  "Lace (window.midnight, no en bundle de voz)",
  "CED Shield: hash + fecha + wallet + kind — no transcript ni PDF bytes",
] as const;
