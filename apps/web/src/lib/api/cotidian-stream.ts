/** Timeouts compartidos — Chat Normal, Finanzas y módulos LIFE vía chat cotidiano. */
/** Generación de imagen (Gemini/Ideogram) puede superar 90s; hard backend ~180s. */
export const COTIDIAN_CHAT_TIMEOUT_MS = 200_000;
/** Stall sin bytes: keepalives de imagen llegan ~cada 8–10s; margen holgado. */
export const COTIDIAN_STREAM_STALL_MS = 90_000;
