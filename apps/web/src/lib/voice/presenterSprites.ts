import type { PresenterGesture } from "@/lib/voice/presenterGestures";

/** Sube este número cuando reemplaces un PNG para saltar la caché del navegador. */
export const PRESENTER_SPRITE_VER = "gestures2";

export type PresenterSpriteSlot = {
  /** Archivo en /public/voice/ced-puppet/ */
  file: `${PresenterGesture}.png`;
  /** Emoción que debe verse en la foto. */
  emotion: string;
  /** Cuándo el robot usa este gesto (voz / orden). */
  command: string;
};

/**
 * Biblioteca 1:1 — una imagen por gesto.
 * Tú generas la foto; se guarda aquí y este mapa la conecta al comando.
 */
export const PRESENTER_SPRITE_SLOTS: Record<PresenterGesture, PresenterSpriteSlot> = {
  idle: {
    file: "idle.png",
    emotion: "Espera, flotando en calma",
    command: "Reposo, entre órdenes",
  },
  welcome: {
    file: "welcome.png",
    emotion: "Saludo, mano alzada",
    command: "Al activar ROBOT, hola, abrir Sistema",
  },
  farewell: {
    file: "farewell.png",
    emotion: "Despedida",
    command: "Al apagar ROBOT, adiós, pasar a ASISTENTE",
  },
  think: {
    file: "think.png",
    emotion: "Pensando, mano al mentón",
    command: "Preguntas, Avanzado, procesar, analizar",
  },
  success: {
    file: "success.png",
    emotion: "Éxito, celebración",
    command: "Finanzas, dinero, listo con ganancia",
  },
  serious: {
    file: "serious.png",
    emotion: "Serio, concentrado",
    command: "Órdenes firmes, presentación formal",
  },
  laugh: {
    file: "laugh.png",
    emotion: "Risa",
    command: "jaja, gracioso, momento cómico",
  },
  listen: {
    file: "listen.png",
    emotion: "Escucha atenta, cabeza inclinada",
    command: "Cuando hablas al micrófono",
  },
  construct: {
    file: "construct.png",
    emotion: "Construyendo / generando",
    command: "Imagen, PDF, historial, diseñar",
  },
  error: {
    file: "error.png",
    emotion: "Confusión, no entendió",
    command: "Error, no entiendo, comando fallido",
  },
  ok: {
    file: "ok.png",
    emotion: "Pulgar arriba, confirmado",
    command: "Cerrar pestaña, listo, okey, hecho",
  },
  point: {
    file: "point.png",
    emotion: "Señala con el brazo",
    command: "Mira aquí, apunta a un botón",
  },
  present: {
    file: "present.png",
    emotion: "Presenta con la palma",
    command: "Abrir Oportunidades, módulos, te presento",
  },
  sad: {
    file: "sad.png",
    emotion: "Triste, disculpa",
    command: "Lo siento, no pude, perdón",
  },
  stress: {
    file: "stress.png",
    emotion: "Estrés, urgencia",
    command: "Auxilio, se rompió, urgencia",
  },
  zen: {
    file: "zen.png",
    emotion: "Calma, respirando",
    command: "Espera, calma, respira, zen",
  },
  look: {
    file: "look.png",
    emotion: "Mirando hacia el objetivo",
    command: "Mira, fíjate, observa, aquí está",
  },
};

export const PRESENTER_GESTURE_IDS = Object.keys(
  PRESENTER_SPRITE_SLOTS,
) as PresenterGesture[];

export function spriteUrl(gesture: PresenterGesture): string {
  const slot = PRESENTER_SPRITE_SLOTS[gesture] ?? PRESENTER_SPRITE_SLOTS.idle;
  return `/voice/ced-puppet/${slot.file}?v=${PRESENTER_SPRITE_VER}`;
}

export function allSpriteUrls(): string[] {
  return PRESENTER_GESTURE_IDS.map((id) => spriteUrl(id));
}
