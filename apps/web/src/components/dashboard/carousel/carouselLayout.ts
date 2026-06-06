/** Tamaños del carrusel HUD — un solo lugar para escalar. */

export const CARD_WIDTH_PX = 390;

export const CARD_HEIGHT_PX = 485;

export const CARD_WIDTH_COMPACT_PX = 325;

export const CARD_HEIGHT_COMPACT_PX = 370;



/** Stage fijo — el cuadro exterior no se mueve. */

export const CAROUSEL_STAGE_INSET_PX = 10;

export const CAROUSEL_HEIGHT_PX = 490;



/** Panel CASTILLO — altura total derivada (header + subtítulo + stage). */

export const CAROUSEL_PANEL_HEADER_PX = 44;

export const CAROUSEL_SUBTITLE_BLOCK_PX = 22;

export const CAROUSEL_BODY_PADDING_Y_PX = 8;

export const CAROUSEL_PANEL_HEIGHT_PX =

  CAROUSEL_PANEL_HEADER_PX +

  CAROUSEL_BODY_PADDING_Y_PX * 2 +

  CAROUSEL_SUBTITLE_BLOCK_PX +

  CAROUSEL_HEIGHT_PX;



export const CAROUSEL_RADIUS = 3.9;

export const CAROUSEL_CAMERA_Z = 7.5;

export const CAROUSEL_RING_Y = 0;



/**

 * Escala visual en pantalla (Three.js Html + transform).

 * Mayor = tarjetas más grandes en el cuadro; no cambia el panel exterior.

 */

export const CAROUSEL_HTML_DISTANCE = 1.62;



/** ~55 s por vuelta completa a 60 fps */

export const CAROUSEL_ROTATION_SPEED = 0.0019;

