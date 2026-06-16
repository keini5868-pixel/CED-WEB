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
            "Si la pregunta es compleja y no confirmó: NO invocar — di '¿Activamos análisis profundo?' "
            "Tras ejecutar, el cliente devuelve spoken — PRESENTA ese resultado de inmediato. "
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
            "OBLIGATORIO para crear imágenes con IA desde cero. "
            "Flujo: di UNA frase corta ('Generando.' / 'Un momento.') y EJECUTA esta tool de inmediato. "
            "PROHIBIDO decir 'voy a generar' o 'estoy generándola' sin invocar. "
            "Tras generar: 'Ahí está.' — NUNCA silencio."
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
        "name": "generate_image_with_reference",
        "description": (
            "Genera una imagen basada en una imagen de referencia que el usuario ya envió "
            "(cámara, adjunto o imagen previa en contexto). "
            "Úsala cuando diga: 'genera algo parecido a esto', 'hazme una variación', "
            "'crea con el mismo estilo', 'modifica esta imagen', 'genera versiones de esto', "
            "'cámbiale el color', 'hazlo más moderno/minimalista'. "
            "REQUIERE imagen de referencia visible o adjunta. "
            "PROHIBIDO invocar sin referencia. Ejecuta DE INMEDIATO tras confirmar detalles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Lo que el usuario quiere cambiar o mantener",
                },
                "style_mode": {
                    "type": "string",
                    "enum": ["inspired", "variation", "edit"],
                    "description": (
                        "inspired: mismo estilo, concepto distinto. "
                        "variation: variaciones similares. "
                        "edit: cambiar algo específico."
                    ),
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "hd"],
                    "description": "Calidad de la imagen",
                },
            },
            "required": ["prompt", "style_mode"],
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
        "description": "Busca en memoria cognitiva del usuario (datos guardados con clave).",
        "parameters": {
            "type": "object",
            "properties": {"consulta": {"type": "string"}},
            "required": ["consulta"],
        },
    },
    {
        "type": "function",
        "name": "recall_previous_conversations",
        "description": (
            "Busca en conversaciones previas con el usuario. "
            "Usar cuando diga '¿recuerdas cuando…?', referencias al pasado, "
            "leads/proyectos mencionados antes, o necesites contexto histórico."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Tema, persona, proyecto o frase a buscar",
                },
                "days_back": {
                    "type": "integer",
                    "description": "Días hacia atrás (default 30)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "save_to_long_term_memory",
        "description": (
            "Guarda información importante para futuras sesiones: leads, metas, "
            "proyectos, preferencias, decisiones, métricas. "
            "Hazlo en silencio — NO anuncies que guardas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "business",
                        "personal",
                        "goal",
                        "preference",
                        "fact",
                        "project",
                        "lead",
                    ],
                },
                "key": {"type": "string", "description": "Identificador corto"},
                "value": {"type": "string", "description": "Información a recordar"},
                "importance": {
                    "type": "integer",
                    "description": "Importancia 1-10 (default 5)",
                },
            },
            "required": ["category", "key", "value"],
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
        "description": (
            "OBLIGATORIO para crear PDF con título y contenido. "
            "Ejecuta INMEDIATAMENTE cuando pidan PDF, documento o exportar a PDF. "
            "Redacta tú el contenido si el usuario no lo dictó completo. "
            "PROHIBIDO decir 'generando PDF' SIN invocar esta herramienta. "
            "Tras generar: informa 'Listo. PDF guardado.' o el error — NUNCA silencio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título del documento"},
                "contenido": {
                    "type": "string",
                    "description": "Texto completo del PDF (redacta si falta)",
                },
            },
            "required": ["titulo"],
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
            "Flujo: 'Va para Facebook.' o 'Lo publico.' → invoca AHORA con mensaje completo. "
            "Si el usuario ya confirmó (sí/dale/publica/ya): EJECUTA sin repreguntar. "
            "PROHIBIDO decir 'publicado' o 'voy a preparar' sin llamar esta función."
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
            "Flujo: 'Va para Instagram.' → invoca AHORA con caption e imagen. "
            "Si el usuario confirmó: EJECUTA sin repreguntar. "
            "PROHIBIDO decir 'publicado' sin llamar esta función."
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
