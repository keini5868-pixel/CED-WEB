"""Tools OpenAI Realtime — esquema JSON."""

from __future__ import annotations

from typing import Any

OPENAI_REALTIME_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_web",
        "description": (
            "Busca en internet SOLO clima actual, noticias de hoy o precios/cotizaciones de hoy. "
            "PROHIBIDO para opiniones, personas, conceptos estables o conocimiento general — usa cerebro interno."
        ),
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
        "name": "generate_image",
        "description": (
            "OBLIGATORIO para crear imágenes con IA desde cero. "
            "Flujo: 'Un momento, Señor.' → EJECUTA tool → 'Imagen generada, Señor.' "
            "PROHIBIDO decir 'voy a generar' sin invocar. Tras generar: confirmación formal con Señor/Señora."
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
            "Activa la cámara del usuario cuando pida visión o quiera mostrar algo. "
            "Usar si dice 'activa la cámara', 'mira esto', '¿qué ves?'. "
            "Tras activar confirma breve: 'Cámara activa.' NO describes nada visual hasta analyze_camera_frame."
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
        "name": "analyze_uploaded_image",
        "description": (
            "Analiza la imagen que el usuario subió al panel de chat de voz (no cámara). "
            "OBLIGATORIO cuando pregunte qué hay en la imagen, pida describirla, caption, "
            "ideas para redes, etc. y hay imagen subida en sesión. "
            "PROHIBIDO inventar contenido visual sin invocar esta herramienta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "Qué quiere saber el usuario sobre la imagen subida",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "analyze_camera_frame",
        "description": (
            "OBLIGATORIO antes de describir algo visual. Captura y analiza el frame de cámara. "
            "Si la cámara está apagada, invoca request_camera_activation primero. "
            "Responde SOLO con el resultado de esta herramienta — PROHIBIDO inventar lo que ves."
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
        "name": "buscar_lo_visible",
        "description": (
            "Busca en internet información sobre lo que muestra la cámara. "
            "Requiere cámara activa (request_camera_activation si hace falta). "
            "OBLIGATORIO invocar esta tool — PROHIBIDO inventar resultados de búsqueda visual."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "Qué buscar sobre lo visible, ej: 'precio de este producto'",
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
            "Tras invocar generar_pdf, DEBES decir explícitamente: "
            "'PDF listo, señor. Título: [título]. ¿Dónde desea guardarlo?' "
            "NUNCA asumas éxito sin confirmar verbalmente. NUNCA quedes en silencio tras crear un PDF."
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
            "required": ["titulo", "contenido"],
        },
    },
    {
        "type": "function",
        "name": "consultar_redes_conectadas",
        "description": (
            "Consulta si el usuario tiene Facebook e Instagram conectados vía Meta OAuth. "
            "Úsala cuando pregunte si puede publicar, si las redes están vinculadas, "
            "o antes de publicar si no estás seguro del estado de conexión. "
            "PROHIBIDO afirmar que está conectado sin invocar esta herramienta."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "leer_comentarios_redes",
        "description": (
            "Úsala SIEMPRE que el usuario quiera saber qué dice la gente, revisar feedback, "
            "leer comentarios de posts, responder a la audiencia o auditar publicaciones de "
            "Instagram y Facebook. Patrón: 'Ok, Señor, un momento.' → invoca AHORA → "
            "informa cuántos comentarios hay y si alguno es caliente (posible cliente). "
            "PROHIBIDO inventar comentarios sin invocar esta herramienta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["both", "instagram", "facebook"],
                    "description": "Red a consultar. Por defecto both.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "activar_prospeccion",
        "description": (
            "Activa modo prospección / perspective mode (Élite+). "
            "SOLO invocar si el usuario dice EXPLÍCITAMENTE 'activa prospección', "
            "'activar modo prospección', 'modo perspectiva' o 'perspective mode'. "
            "PROHIBIDO invocar en saludos, '¿cómo estás?', charla casual o frases con 'sí'."
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
            "Patrón Jarvis: 1 frase formal ANTES (ej. 'Procediendo con la publicación') "
            "→ invoca AHORA con mensaje completo → DESPUÉS di en voz la confirmación del campo spoken. "
            "PROHIBIDO: 'Va', 'Va para Facebook', 'Ok', 'Listo', 'Dale', 'Hecho'. "
            "PROHIBIDO omitir la confirmación tras ejecutar. "
            "Si el usuario ya confirmó (sí/publica/ya): EJECUTA sin repreguntar."
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
            "Patrón Jarvis: 1 frase formal ANTES (ej. 'Procediendo con la publicación en Instagram') "
            "→ invoca AHORA con caption e imagen → DESPUÉS di en voz la confirmación del campo spoken. "
            "PROHIBIDO: 'Va', 'Va para Instagram', 'Ok', 'Listo', 'Dale'. "
            "PROHIBIDO omitir la confirmación tras ejecutar. "
            "Si el usuario confirmó: EJECUTA sin repreguntar."
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
    {
        "type": "function",
        "name": "search_nearby_places",
        "description": (
            "Busca lugares cercanos SIN pedir dirección completa al usuario. "
            "OBLIGATORIO cuando digan: llévame a X, busca X cerca, dónde hay X, "
            "quiero ir a un Walmart/gasolinera/farmacia. "
            "Muestra hasta 3 opciones en pantalla y explícalas por voz. "
            "NUNCA pidas la dirección — búscala tú."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nombre del lugar o negocio (ej. Walmart, Starbucks)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "start_navigation",
        "description": (
            "Inicia navegación paso a paso hacia el destino elegido. "
            "Usar cuando digan: el primero, el segundo, el tercero, iniciar viaje, "
            "vamos al más cercano, o confirmen una opción de la lista en pantalla. "
            "Si piden ir a un lugar genérico (ej. Walmart), primero usa search_nearby_places."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destino": {
                    "type": "string",
                    "description": "Destino o elección (ej. el primero, Walmart)",
                },
                "index": {
                    "type": "integer",
                    "description": "Índice 0-based de la opción en pantalla",
                },
                "opcion": {"type": "string", "description": "primero, segundo, tercero"},
            },
        },
    },
    {
        "type": "function",
        "name": "stop_navigation",
        "description": (
            "Detiene la navegación activa. "
            "Usar cuando digan: detén la navegación, ya llegué, cancela el viaje, "
            "para de guiarme."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "navigation_status",
        "description": (
            "Informa el estado de la navegación: próximo paso, distancia al giro, "
            "tiempo restante. Usar cuando digan: ¿cuánto falta?, ¿qué sigue?, "
            "¿cuánto tiempo?"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "activar_modo_conducir",
        "description": (
            "Abre el mapa GPS / modo conducir de CED. "
            "Usar cuando digan: abre el mapa, modo conducir, navegar, GPS, guíame, "
            "quiero que me guíes, activa navegación. "
            "Si ya están en el mapa, confirma que está activo."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "buscar_direccion",
        "description": (
            "Busca una dirección o lugar y la muestra en el mapa. "
            "Usar cuando digan: busca X, dónde queda X, encuentra la dirección de X."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Dirección o nombre del lugar"},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "iniciar_navegacion",
        "description": (
            "Alias de start_navigation — calcula ruta y activa guía paso a paso. "
            "Para lugares genéricos (Walmart, farmacia): primero search_nearby_places. "
            "NUNCA pidas dirección completa al usuario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destino": {
                    "type": "string",
                    "description": "Dirección o lugar de destino",
                },
            },
            "required": ["destino"],
        },
    },
    {
        "type": "function",
        "name": "cancelar_navegacion",
        "description": (
            "Cancela la ruta activa y deja de guiar. "
            "Usar cuando digan: cancela ruta, ya no navegues, detén la guía."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "estado_navegacion",
        "description": "Informa distancia, tiempo restante o si hay ruta activa.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def build_openai_chat_tools() -> list[dict[str, Any]]:
    """Convierte esquemas Realtime al formato Chat Completions de OpenAI."""
    out: list[dict[str, Any]] = []
    for tool in OPENAI_REALTIME_TOOLS:
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "parameters": tool.get("parameters")
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return out

