/** Timeouts compartidos — Chat Normal, Finanzas y módulos LIFE vía chat cotidiano. */
/** Generación de imagen (Gemini/Ideogram); hard backend ~210s + margen proxy. */
export const COTIDIAN_CHAT_TIMEOUT_MS = 280_000;
/** Stall sin bytes: keepalives de imagen llegan ~cada 5s; margen holgado. */
export const COTIDIAN_STREAM_STALL_MS = 120_000;
