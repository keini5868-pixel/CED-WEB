"""Tools OpenAI Realtime — esquema JSON."""

from __future__ import annotations

from typing import Any

OPENAI_REALTIME_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_web",
        "description": "Busca información actual en internet (clima, noticias, precios).",
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
        "description": "Análisis profundo. Invocar solo si el usuario confirmó o pidió explícitamente el sistema avanzado. No invocar para clima/noticias.",
        "parameters": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "type": "function",
        "name": "generate_image",
        "description": "Genera imagen con IA. quality: auto|standard|hd.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "quality": {"type": "string", "enum": ["auto", "standard", "hd"]},
            },
            "required": ["prompt"],
        },
    },
    {
        "type": "function",
        "name": "save_memory",
        "description": "Guarda un dato en memoria cognitiva.",
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
        "name": "analyze_camera_frame",
        "description": "Analiza lo visible en cámara (Pro+). Requiere cámara activa.",
        "parameters": {
            "type": "object",
            "properties": {"pregunta": {"type": "string"}},
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
        "description": "Activa modo prospección Instagram (Élite+).",
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
        "description": "Publica en Facebook conectado.",
        "parameters": {
            "type": "object",
            "properties": {
                "mensaje": {"type": "string"},
                "image_url": {"type": "string"},
            },
            "required": ["mensaje"],
        },
    },
    {
        "type": "function",
        "name": "publicar_instagram",
        "description": "Publica en Instagram con imagen URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "caption": {"type": "string"},
                "image_url": {"type": "string"},
            },
            "required": ["caption", "image_url"],
        },
    },
]
