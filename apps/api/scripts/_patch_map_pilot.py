"""Wire map/navigation tools into retell_native_pilot.py"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "retell_native_pilot.py"
text = PATH.read_text(encoding="utf-8")

if "def build_open_drive_map_tool" in text:
    print("map already patched")
    raise SystemExit(0)

# Prompt tools
text = text.replace(
    "- read_social_comments: leer comentarios recientes FB/IG.\n",
    "- read_social_comments: leer comentarios recientes FB/IG.\n"
    "- open_drive_map: abrir mapa / modo conducir.\n"
    "- search_nearby_places: buscar destino («llévame a …»).\n"
    "- show_route: mostrar ruta calculada («muéstrame la ruta»).\n"
    "- start_drive_navigation: iniciar navegación en vivo («inicia la ruta»).\n"
    "- stop_drive_navigation: detener navegación.\n"
    "- navigation_status: estado/ETA de la ruta.\n",
    1,
)

if "Prospección (leads" in text and "Mapa / navegación:" not in text:
    text = text.replace(
        "5. Requiere Meta conectado y plan con prospección; si falla, di el mensaje de la tool.\n\n"
        "Búsqueda web (search_web):",
        "5. Requiere Meta conectado y plan con prospección; si falla, di el mensaje de la tool.\n\n"
        "Mapa / navegación:\n"
        "1. «llévame a [lugar]» → search_nearby_places (abre mapa si hace falta).\n"
        "2. «muéstrame la ruta» → show_route (traza la ruta; aún no inicia guía).\n"
        "3. «inicia la ruta / inicia la navegación» → start_drive_navigation.\n"
        "4. «abre el mapa / modo conducir» → open_drive_map.\n"
        "5. «detén la navegación / cancela ruta» → stop_drive_navigation.\n\n"
        "Búsqueda web (search_web):",
        1,
    )

if "- Prospección:" in text and "Mapa:" not in text.split("Estado general")[1][:1200]:
    text = text.replace(
        "- Prospección: enable_prospection / disable_prospection / prospection_report / read_social_comments.\n",
        "- Prospección: enable_prospection / disable_prospection / prospection_report / read_social_comments.\n"
        "- Mapa: open_drive_map, search_nearby_places, show_route, start_drive_navigation, stop_drive_navigation, navigation_status.\n",
        1,
    )

# Descriptions
anchor = (
    'READ_SOCIAL_COMMENTS_DESCRIPTION = (\n'
    '    "Lee comentarios recientes de Instagram y/o Facebook y destaca prospectos calientes."\n'
    ')\n'
)
if anchor not in text:
    raise SystemExit("READ_SOCIAL_COMMENTS_DESCRIPTION missing")
text = text.replace(
    anchor,
    anchor
    + """
OPEN_DRIVE_MAP_DESCRIPTION = (
    "Abre el mapa / modo conducir en pantalla."
)
SEARCH_NEARBY_PLACES_DESCRIPTION = (
    "Busca lugares cercanos o un destino. Usar con «llévame a …»."
)
SHOW_ROUTE_DESCRIPTION = (
    "Calcula y muestra la ruta al destino (sin iniciar guía aún). Usar con «muéstrame la ruta»."
)
START_DRIVE_NAVIGATION_DESCRIPTION = (
    "Inicia la navegación en vivo con zoom, flecha y guía hablada. Usar con «inicia la ruta»."
)
STOP_DRIVE_NAVIGATION_DESCRIPTION = "Detiene la navegación y limpia la ruta activa."
NAVIGATION_STATUS_DESCRIPTION = "Informa el estado de la navegación (ETA, destino, si está guiando)."
""",
    1,
)

params_anchor = (
    "READ_SOCIAL_COMMENTS_PARAMETERS: dict[str, Any] = {\n"
    '    "type": "object",\n'
    '    "properties": {\n'
    '        "platform": {\n'
    '            "type": "string",\n'
    '            "description": "both, instagram o facebook. Por defecto both.",\n'
    "        },\n"
    "    },\n"
    "}\n"
)
if params_anchor not in text:
    raise SystemExit("READ_SOCIAL_COMMENTS_PARAMETERS missing")
text = text.replace(
    params_anchor,
    params_anchor
    + """
OPEN_DRIVE_MAP_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
SEARCH_NEARBY_PLACES_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Lugar o destino."},
    },
    "required": ["query"],
}
SHOW_ROUTE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Destino opcional si aún no hay ruta."},
        "option_index": {"type": "integer", "description": "Índice 0-based de la opción en pantalla."},
    },
}
START_DRIVE_NAVIGATION_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
STOP_DRIVE_NAVIGATION_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
NAVIGATION_STATUS_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}
""",
    1,
)

# Builders after read_social_comments
builder_anchor = '''def build_read_social_comments_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="read_social_comments",
        description=READ_SOCIAL_COMMENTS_DESCRIPTION,
        parameters=READ_SOCIAL_COMMENTS_PARAMETERS,
        filler="Leyendo comentarios, señor.",
        timeout_ms=25_000,
    )


'''
if builder_anchor not in text:
    raise SystemExit("builder anchor missing")
text = text.replace(
    builder_anchor,
    builder_anchor
    + '''def build_open_drive_map_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="open_drive_map",
        description=OPEN_DRIVE_MAP_DESCRIPTION,
        parameters=OPEN_DRIVE_MAP_PARAMETERS,
        filler="Abriendo el mapa, señor.",
        timeout_ms=8_000,
    )


def build_search_nearby_places_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_nearby_places",
        description=SEARCH_NEARBY_PLACES_DESCRIPTION,
        parameters=SEARCH_NEARBY_PLACES_PARAMETERS,
        filler="Buscando el destino, señor.",
        timeout_ms=20_000,
    )


def build_show_route_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="show_route",
        description=SHOW_ROUTE_DESCRIPTION,
        parameters=SHOW_ROUTE_PARAMETERS,
        filler="Calculando la ruta, señor.",
        timeout_ms=25_000,
    )


def build_start_drive_navigation_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="start_drive_navigation",
        description=START_DRIVE_NAVIGATION_DESCRIPTION,
        parameters=START_DRIVE_NAVIGATION_PARAMETERS,
        filler="Iniciando navegación, señor.",
        timeout_ms=15_000,
    )


def build_stop_drive_navigation_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="stop_drive_navigation",
        description=STOP_DRIVE_NAVIGATION_DESCRIPTION,
        parameters=STOP_DRIVE_NAVIGATION_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_navigation_status_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="navigation_status",
        description=NAVIGATION_STATUS_DESCRIPTION,
        parameters=NAVIGATION_STATUS_PARAMETERS,
        filler="Revisando la ruta, señor.",
        timeout_ms=8_000,
    )


''',
    1,
)

# General tools
text = text.replace(
    "                build_read_social_comments_tool(api_public_url=api_public_url),\n",
    "                build_read_social_comments_tool(api_public_url=api_public_url),\n"
    "                build_open_drive_map_tool(api_public_url=api_public_url),\n"
    "                build_search_nearby_places_tool(api_public_url=api_public_url),\n"
    "                build_show_route_tool(api_public_url=api_public_url),\n"
    "                build_start_drive_navigation_tool(api_public_url=api_public_url),\n"
    "                build_stop_drive_navigation_tool(api_public_url=api_public_url),\n"
    "                build_navigation_status_tool(api_public_url=api_public_url),\n",
    1,
)

# Metrics
text = text.replace(
    '        "read_social_comments": _stats("read_social_comments"),\n',
    '        "read_social_comments": _stats("read_social_comments"),\n'
    '        "open_drive_map": _stats("open_drive_map"),\n'
    '        "search_nearby_places": _stats("search_nearby_places"),\n'
    '        "show_route": _stats("show_route"),\n'
    '        "start_drive_navigation": _stats("start_drive_navigation"),\n'
    '        "stop_drive_navigation": _stats("stop_drive_navigation"),\n'
    '        "navigation_status": _stats("navigation_status"),\n',
    1,
)

# Executors before compat alias
exec_anchor = "# Compat tests / imports previos\nresolve_environment_tool_query = resolve_tool_query\n"
if exec_anchor not in text:
    raise SystemExit("exec anchor missing")
text = text.replace(
    exec_anchor,
    '''
async def execute_open_drive_map_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="open_drive_map",
        voice_tool_name="activar_modo_conducir",
        user_id=user_id,
        payload=payload,
    )


async def execute_search_nearby_places_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip() or resolve_tool_query(payload, args)
    return await _execute_native_voice_alias_tool(
        tool_name="search_nearby_places",
        voice_tool_name="search_nearby_places",
        user_id=user_id,
        payload=payload,
        args={"query": query, "_user_request": query},
    )


async def execute_show_route_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Muestra ruta: usa opción pendiente/índice o destino en query; no inicia guía."""
    params: dict[str, Any] = {}
    if args.get("option_index") is not None:
        params["option_index"] = int(args["option_index"])
    query = str(args.get("query") or "").strip() or resolve_tool_query(payload, args)
    if query and query.lower() not in {
        "muestrame la ruta",
        "muéstrame la ruta",
        "mostrar la ruta",
        "muestra la ruta",
        "la ruta",
    }:
        params["destino"] = query
    # Sin confirm: _start_route preview; si ya hay ruta, start_navigation responde mensaje.
    return await _execute_native_voice_alias_tool(
        tool_name="show_route",
        voice_tool_name="start_navigation",
        user_id=user_id,
        payload=payload,
        args=params,
    )


async def execute_start_drive_navigation_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="start_drive_navigation",
        voice_tool_name="start_navigation",
        user_id=user_id,
        payload=payload,
        args={"confirm": True, "destino": "iniciar"},
    )


async def execute_stop_drive_navigation_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="stop_drive_navigation",
        voice_tool_name="stop_navigation",
        user_id=user_id,
        payload=payload,
    )


async def execute_navigation_status_tool(*, user_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return await _execute_native_voice_alias_tool(
        tool_name="navigation_status",
        voice_tool_name="navigation_status",
        user_id=user_id,
        payload=payload,
    )


# Compat tests / imports previos
resolve_environment_tool_query = resolve_tool_query
''',
    1,
)

PATH.write_text(text, encoding="utf-8")
print("map pilot patch ok")
