/** Herramientas Gemini Live — CED Web. */

import { Type, type FunctionDeclaration } from "@google/genai";

export const CONSULTAR_SISTEMA_AVANZADO = "consultar_sistema_avanzado";
export const GUARDAR_MEMORIA = "guardar_memoria";
export const BUSCAR_MEMORIA = "buscar_memoria";
export const ACTIVAR_PROSPECCION = "activar_prospeccion";
export const DESACTIVAR_PROSPECCION = "desactivar_prospeccion";
export const REPORTE_PROSPECCION = "reporte_prospeccion";
export const BUSCAR_LO_VISIBLE = "buscar_lo_visible";
export const ANALIZAR_CAMARA = "analyze_camera_frame";
export const PUBLICAR_FACEBOOK = "publicar_facebook";
export const PUBLICAR_INSTAGRAM = "publicar_instagram";
export const GENERAR_PDF = "generar_pdf";

export const LIVE_FUNCTION_DECLARATIONS: FunctionDeclaration[] = [
  {
    name: CONSULTAR_SISTEMA_AVANZADO,
    description:
      "SOLO tras confirmación explícita (sí/adelante). NUNCA para clima, noticias, búsquedas web ni datos de hoy.",
    parameters: {
      type: Type.OBJECT,
      properties: {
        prompt: {
          type: Type.STRING,
          description: "Consulta para el sistema avanzado.",
        },
      },
      required: ["prompt"],
    },
  },
  {
    name: GUARDAR_MEMORIA,
    description:
      "Guarda un hecho, preferencia o dato importante del usuario en memoria cognitiva persistente.",
    parameters: {
      type: Type.OBJECT,
      properties: {
        clave: {
          type: Type.STRING,
          description: "Identificador corto, ej: 'nicho_negocio', 'meta_2026'.",
        },
        contenido: {
          type: Type.STRING,
          description: "Texto a recordar.",
        },
        categoria: {
          type: Type.STRING,
          description: "Opcional: negocio, personal, preferencia.",
        },
      },
      required: ["clave", "contenido"],
    },
  },
  {
    name: BUSCAR_MEMORIA,
    description: "Recupera memorias guardadas del usuario por palabra clave.",
    parameters: {
      type: Type.OBJECT,
      properties: {
        consulta: {
          type: Type.STRING,
          description: "Término de búsqueda o vacío para listar recientes.",
        },
      },
      required: ["consulta"],
    },
  },
  {
    name: ACTIVAR_PROSPECCION,
    description:
      "Activa modo prospección 24/7: escanea comentarios Instagram en busca de leads.",
    parameters: { type: Type.OBJECT, properties: {} },
  },
  {
    name: DESACTIVAR_PROSPECCION,
    description: "Desactiva el modo prospección.",
    parameters: { type: Type.OBJECT, properties: {} },
  },
  {
    name: REPORTE_PROSPECCION,
    description: "Informe de leads detectados hoy y estado de prospección.",
    parameters: { type: Type.OBJECT, properties: {} },
  },
  {
    name: BUSCAR_LO_VISIBLE,
    description:
      "SOLO si la cámara está activa. Identifica lo que ve el usuario y busca en internet (Tavily).",
    parameters: {
      type: Type.OBJECT,
      properties: {
        pregunta: {
          type: Type.STRING,
          description: "Pregunta opcional sobre lo visible, ej: 'precio', 'qué es'.",
        },
      },
    },
  },
  {
    name: PUBLICAR_FACEBOOK,
    description:
      "Publica en la página de Facebook conectada. Requiere mensaje de texto; imagen opcional (URL HTTPS pública).",
    parameters: {
      type: Type.OBJECT,
      properties: {
        mensaje: { type: Type.STRING, description: "Texto de la publicación." },
        image_url: {
          type: Type.STRING,
          description: "URL pública HTTPS de imagen opcional.",
        },
      },
      required: ["mensaje"],
    },
  },
  {
    name: PUBLICAR_INSTAGRAM,
    description:
      "Publica en Instagram Business conectado. Requiere caption e image_url HTTPS pública.",
    parameters: {
      type: Type.OBJECT,
      properties: {
        caption: { type: Type.STRING, description: "Texto de la publicación." },
        image_url: {
          type: Type.STRING,
          description: "URL pública HTTPS de la imagen (obligatoria).",
        },
      },
      required: ["caption", "image_url"],
    },
  },
  {
    name: GENERAR_PDF,
    description:
      "Genera un PDF con el contenido indicado y lo guarda en el historial de la sesión para descarga.",
    parameters: {
      type: Type.OBJECT,
      properties: {
        titulo: {
          type: Type.STRING,
          description: "Título del documento PDF.",
        },
        contenido: {
          type: Type.STRING,
          description: "Texto COMPLETO del cuerpo del PDF — toda la información a exportar.",
        },
      },
      required: ["titulo", "contenido"],
    },
  },
];

export const LIVE_TOOL_NAMES = new Set([
  ...(LIVE_FUNCTION_DECLARATIONS.map((d) => d.name).filter(Boolean) as string[]),
  ANALIZAR_CAMARA,
]);
