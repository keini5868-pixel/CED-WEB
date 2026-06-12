"""Tools OpenAI Realtime — esquema JSON."""

from __future__ import annotations

from typing import Any

OPENAI_REALTIME_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_web",
        "description": "Busca información actual en internet (clima, noticias, precios). NO usar para análisis profundo.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta de búsqueda."},
                "kind": {
                    "type": "string",
                    "enum": ["news", "weather", "general"],
                    "description": "Tipo de búsqueda.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "consultar_claude",
        "description": (
            "Sistema avanzado para análisis profundo. "
            "SOLO tras confirmación del usuario o petición explícita. "
            "Si la pregunta es compleja y no confirmó: NO invocar — pregunta primero. "
            "NUNCA para clima, noticias ni búsquedas web."
        ),
        "parameters": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "type": "function",
        "name": "generate_image",
        "description": (
            "Genera imagen con IA a partir de una descripción. "
            "Usar cuando pidan crear/diseñar/generar una imagen. "
            "Tras generar, la imagen queda lista para publicar en redes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Descripción detallada de la imagen."},
                "quality": {"type": "string", "enum": ["auto", "standard", "hd"]},
            },
            "required": ["prompt"],
        },
    },
    {
        "type": "function",
        "name": "save_memory",
        "description": (
            "Guarda un dato en memoria cognitiva. "
            "Para cómo llamar al usuario usa key \"tratamiento\" (ej. Señor, Señora, Jefe)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "clave": {"type": "string"},
                "contenido": {"type": "string"},
                "categoria": {"type": "string"},
            },
            "required": ["clave", "contenido"],
        },
    },
    {
        "type": "function",
        "name": "recall_memory",
        "description": "Busca en memoria cognitiva del usuario.",
        "parameters": {
            "type": "object",
            "properties": {"consulta": {"type": "string"}},
            "required": ["consulta"],
        },
    },
    {
        "type": "function",
        "name": "request_camera_activation",
        "description": (
            "Activa la cámara del usuario para que puedas VER lo que muestra. "
            "Usar cuando diga 'activa la cámara', 'enciende la cámara', "
            "'quiero mostrarte algo', 'mira esto', 'puedes ver esto'. "
            "El cliente enciende la cámara y envía frames — NO simules encender."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Motivo breve de activación",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "request_camera_deactivation",
        "description": (
            "Desactiva la cámara cuando el usuario diga 'apaga la cámara', "
            "'desactiva la cámara' o 'deja de mirar'."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "analyze_camera_frame",
        "description": (
            "OBLIGATORIO cuando el usuario pregunta qué ves en cámara o qué hay frente a la cámara. "
            "Captura y analiza el frame actual. Requiere cámara activa (activarla si hace falta). "
            "PROHIBIDO decir que no puedes ver sin invocar esta herramienta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "Pregunta del usuario sobre lo visible, ej: '¿qué es esto?'",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "generar_pdf",
        "description": "Genera PDF con título y contenido completo.",
        "parameters": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "contenido": {"type": "string"},
            },
            "required": ["titulo", "contenido"],
        },
    },
    {
        "type": "function",
        "name": "activar_prospeccion",
        "description": (
            "Activa modo prospección / perspective mode (Élite+). "
            "Usar cuando digan 'activa modo prospección', 'modo perspectiva' o 'perspective mode'."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "desactivar_prospeccion",
        "description": "Desactiva prospección.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "reporte_prospeccion",
        "description": "Reporte de leads de prospección.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "publicar_facebook",
        "description": (
            "OBLIGATORIO para publicar en Facebook. "
            "Acepta texto + imagen opcional (image_data base64, cámara o imagen generada). "
            "NO pidas URL al usuario — usa image_data o from_camera=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mensaje": {"type": "string"},
                "image_url": {"type": "string", "description": "Opcional si hay URL http"},
                "image_data": {"type": "string", "description": "Data URL o base64 — preferido"},
                "from_camera": {
                    "type": "boolean",
                    "description": "True para usar lo que muestra la cámara ahora",
                },
                "use_last_image": {
                    "type": "boolean",
                    "description": "True para usar la última imagen generada",
                },
            },
            "required": ["mensaje"],
        },
    },
    {
        "type": "function",
        "name": "publicar_instagram",
        "description": (
            "OBLIGATORIO para publicar en Instagram. "
            "Requiere caption e imagen (image_data, from_camera o use_last_image). "
            "NO pidas URL HTTPS al usuario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caption": {"type": "string"},
                "image_url": {"type": "string"},
                "image_data": {"type": "string"},
                "from_camera": {"type": "boolean"},
                "use_last_image": {"type": "boolean"},
            },
            "required": ["caption"],
        },
    },
]
