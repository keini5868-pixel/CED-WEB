"""Patch retell_native_pilot.py — Meta publish prepare/confirm tools + state."""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "retell_native_pilot.py"
text = PATH.read_text(encoding="utf-8")

if "def build_meta_prepare_publish_tool" in text and "meta_prepare_publish" in text:
    print("meta already patched")
    raise SystemExit(0)

# --- Prompt tools list ---
needle = "- search_web: búsqueda web general"
if needle in text and "meta_prepare_publish" not in text.split(needle)[0][-200:]:
    text = text.replace(
        needle,
        "- meta_prepare_publish: preparar borrador de publicación FB/IG (NUNCA publica).\n"
        "- meta_confirm_publish: publicar SOLO tras confirmación explícita en voz.\n"
        "- meta_cancel_publish: descartar borrador de publicación.\n"
        "- check_meta_networks: comprobar si Facebook/Instagram están conectados.\n"
        + needle,
        1,
    )

# --- Rules ---
if "Gmail envío: prepare" in text and "Meta publicación:" not in text:
    text = text.replace(
        "- Gmail envío: prepare → confirmación → confirm_send. NUNCA inventes que ya se envió.\n"
        "- PROHIBIDO llamar gmail_confirm_send en el mismo turno que gmail_prepare_send.\n",
        "- Gmail envío: prepare → confirmación → confirm_send. NUNCA inventes que ya se envió.\n"
        "- PROHIBIDO llamar gmail_confirm_send en el mismo turno que gmail_prepare_send.\n"
        "- Meta publicación: prepare → confirmación → confirm_publish. NUNCA inventes que ya se publicó.\n"
        "- PROHIBIDO llamar meta_confirm_publish en el mismo turno que meta_prepare_publish.\n",
        1,
    )

# --- Block with Meta rules ---
if "Búsqueda web (search_web):" in text and "Meta / redes (publicación):" not in text:
    text = text.replace(
        "Búsqueda web (search_web):",
        "Meta / redes (publicación):\n"
        "1. «publica en Facebook/Instagram que diga …» → meta_prepare_publish.\n"
        "2. Tras prepare (awaiting_confirmation): lee el resumen y pregunta; transition_to_publish_confirm_pending.\n"
        "3. «sí» / «publícalo» → meta_confirm_publish (también en general si no transicionó).\n"
        "4. «no / cancela» → meta_cancel_publish.\n"
        "5. Si falta Meta/OAuth, comunica el mensaje de la tool tal cual (Conectar Redes).\n"
        "6. Instagram sin imagen: comunica needs_image; no inventes la publicación.\n"
        "7. check_meta_networks si pregunta si están conectadas las redes.\n\n"
        "Búsqueda web (search_web):",
        1,
    )

# --- General state prompt ---
if "Estado general — clima, calendario, Gmail" in text and "Meta publicación" not in text.split("Estado general")[1][:800]:
    text = text.replace(
        "Estado general — clima, calendario, Gmail, finanzas, búsqueda web, cámara, modo avanzado.",
        "Estado general — clima, calendario, Gmail, finanzas, Meta/redes, búsqueda web, cámara, modo avanzado.",
        1,
    )
    if "- search_web:" in text and "meta_prepare_publish" not in text.split("Estado general")[1][:900]:
        text = text.replace(
            "- search_web: hechos actuales / noticias / datos externos (no clima → get_environment; no cámara → search_visible_product).\n",
            "- search_web: hechos actuales / noticias / datos externos (no clima → get_environment; no cámara → search_visible_product).\n"
            "- Meta: meta_prepare_publish → confirmar → meta_confirm_publish. check_meta_networks para estado de conexión.\n"
            "- Tras meta_prepare_publish con awaiting_confirmation: transition_to_publish_confirm_pending.\n"
            "- Si hay borrador Meta y dice «sí», llama meta_confirm_publish de inmediato (también aquí).\n",
            1,
        )

# --- State constants ---
if 'STATE_GMAIL_CONFIRM_PENDING = "gmail_confirm_pending"' in text and "STATE_PUBLISH_CONFIRM_PENDING" not in text:
    text = text.replace(
        'STATE_GMAIL_CONFIRM_PENDING = "gmail_confirm_pending"\n',
        'STATE_GMAIL_CONFIRM_PENDING = "gmail_confirm_pending"\n'
        'STATE_PUBLISH_CONFIRM_PENDING = "publish_confirm_pending"\n'
        "PUBLISH_CONFIRM_STATE_PROMPT = \"\"\"\n"
        "Estado de confirmación de publicación — hay un borrador FB/IG pendiente.\n"
        "- Si dice sí, publícalo, dale o confirma → meta_confirm_publish (incluso solo «sí»).\n"
        "- Si dice no/cancela → meta_cancel_publish y transition_to_general_assistant.\n"
        "- Tras publicar, di exactamente el mensaje de la herramienta.\n"
        "\"\"\".strip()\n\n",
        1,
    )

# --- Descriptions / parameters before READ_FINANCES or after SEARCH_WEB ---
if "SEARCH_WEB_DESCRIPTION" in text and "META_PREPARE_DESCRIPTION" not in text:
    text = text.replace(
        "SEARCH_WEB_DESCRIPTION = (",
        "META_PREPARE_DESCRIPTION = (\n"
        "    \"Prepara un borrador de publicación en Facebook o Instagram. \"\n"
        "    \"NO publica — pide confirmación. Requiere plataforma y texto (caption). \"\n"
        "    \"Instagram requiere imagen previa (cámara o generada).\"\n"
        ")\n\n"
        "META_CONFIRM_DESCRIPTION = (\n"
        "    \"Publica el borrador pendiente tras confirmación explícita: sí, publícalo, dale. \"\n"
        "    \"Un solo «sí» basta.\"\n"
        ")\n\n"
        "META_CANCEL_DESCRIPTION = (\n"
        "    \"Cancela el borrador de publicación pendiente sin publicarlo.\"\n"
        ")\n\n"
        "CHECK_META_DESCRIPTION = (\n"
        "    \"Comprueba si Facebook e Instagram están conectados (Meta OAuth).\"\n"
        ")\n\n"
        "SEARCH_WEB_DESCRIPTION = (",
        1,
    )

if "SEARCH_WEB_PARAMETERS" in text and "META_PREPARE_PARAMETERS" not in text:
    text = text.replace(
        "SEARCH_WEB_PARAMETERS: dict[str, Any] = {",
        "META_PREPARE_PARAMETERS: dict[str, Any] = {\n"
        "    \"type\": \"object\",\n"
        "    \"properties\": {\n"
        "        \"platform\": {\n"
        "            \"type\": \"string\",\n"
        "            \"description\": \"facebook o instagram\",\n"
        "        },\n"
        "        \"caption\": {\n"
        "            \"type\": \"string\",\n"
        "            \"description\": \"Texto a publicar.\",\n"
        "        },\n"
        "        \"query\": {\n"
        "            \"type\": \"string\",\n"
        "            \"description\": \"Frase completa del usuario si no se separaron platform/caption.\",\n"
        "        },\n"
        "    },\n"
        "}\n\n"
        "META_CONFIRM_PARAMETERS: dict[str, Any] = {\n"
        "    \"type\": \"object\",\n"
        "    \"properties\": {\n"
        "        \"draft_id\": {\n"
        "            \"type\": \"string\",\n"
        "            \"description\": \"ID del borrador de meta_prepare_publish (opcional).\",\n"
        "        },\n"
        "    },\n"
        "}\n\n"
        "META_CANCEL_PARAMETERS: dict[str, Any] = {\n"
        "    \"type\": \"object\",\n"
        "    \"properties\": {\n"
        "        \"draft_id\": {\"type\": \"string\", \"description\": \"ID del borrador (opcional).\"},\n"
        "    },\n"
        "}\n\n"
        "CHECK_META_PARAMETERS: dict[str, Any] = {\"type\": \"object\", \"properties\": {}}\n\n"
        "SEARCH_WEB_PARAMETERS: dict[str, Any] = {",
        1,
    )

# --- Builders after build_search_web_tool ---
if "def build_search_web_tool" in text and "def build_meta_prepare_publish_tool" not in text:
    insert_after = '''def build_search_web_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_web",
        description=SEARCH_WEB_DESCRIPTION,
        parameters=SEARCH_WEB_PARAMETERS,
        filler="Investigando, señor.",
        timeout_ms=25_000,
    )


'''
    builders = '''def build_search_web_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_web",
        description=SEARCH_WEB_DESCRIPTION,
        parameters=SEARCH_WEB_PARAMETERS,
        filler="Investigando, señor.",
        timeout_ms=25_000,
    )


def build_meta_prepare_publish_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="meta_prepare_publish",
        description=META_PREPARE_DESCRIPTION,
        parameters=META_PREPARE_PARAMETERS,
        filler="Preparando la publicación, señor.",
        timeout_ms=12_000,
    )


def build_meta_confirm_publish_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="meta_confirm_publish",
        description=META_CONFIRM_DESCRIPTION,
        parameters=META_CONFIRM_PARAMETERS,
        filler="Publicando, señor.",
        timeout_ms=35_000,
    )


def build_meta_cancel_publish_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="meta_cancel_publish",
        description=META_CANCEL_DESCRIPTION,
        parameters=META_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_check_meta_networks_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="check_meta_networks",
        description=CHECK_META_DESCRIPTION,
        parameters=CHECK_META_PARAMETERS,
        filler="Revisando sus redes, señor.",
        timeout_ms=10_000,
    )


'''
    if insert_after not in text:
        raise SystemExit("build_search_web_tool block not found exactly")
    text = text.replace(insert_after, builders, 1)

# --- General tools list ---
if "build_search_web_tool(api_public_url=api_public_url)," in text and "build_meta_prepare_publish_tool" not in text.split("build_native_pilot_states")[1][:2500]:
    text = text.replace(
        "                build_search_web_tool(api_public_url=api_public_url),\n",
        "                build_search_web_tool(api_public_url=api_public_url),\n"
        "                build_check_meta_networks_tool(api_public_url=api_public_url),\n"
        "                build_meta_prepare_publish_tool(api_public_url=api_public_url),\n"
        "                build_meta_confirm_publish_tool(api_public_url=api_public_url),\n"
        "                build_meta_cancel_publish_tool(api_public_url=api_public_url),\n",
        1,
    )

# --- Edge for publish confirm ---
if "destination_state_name\": STATE_GMAIL_CONFIRM_PENDING" in text and "STATE_PUBLISH_CONFIRM_PENDING" not in text.split("edges")[1][:1500]:
    text = text.replace(
        """                {
                    "destination_state_name": STATE_GMAIL_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando gmail_prepare_send devuelve awaiting_confirmation."
                    ),
                },
""",
        """                {
                    "destination_state_name": STATE_GMAIL_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando gmail_prepare_send devuelve awaiting_confirmation."
                    ),
                },
                {
                    "destination_state_name": STATE_PUBLISH_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando meta_prepare_publish devuelve awaiting_confirmation."
                    ),
                },
""",
        1,
    )

# --- State block after gmail confirm state ---
if 'name": STATE_GMAIL_CONFIRM_PENDING' in text and "STATE_PUBLISH_CONFIRM_PENDING" not in text.split("STATE_GMAIL_CONFIRM_PENDING")[2][:800]:
    gmail_state_end = '''        {
            "name": STATE_GMAIL_CONFIRM_PENDING,
            "state_prompt": GMAIL_CONFIRM_STATE_PROMPT,
            "tools": [
                build_read_gmail_tool(api_public_url=api_public_url),
                build_gmail_confirm_send_tool(api_public_url=api_public_url),
                build_gmail_cancel_send_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras enviar, cancelar o borrador expirado."
                    ),
                },
            ],
        },
'''
    publish_state = '''        {
            "name": STATE_GMAIL_CONFIRM_PENDING,
            "state_prompt": GMAIL_CONFIRM_STATE_PROMPT,
            "tools": [
                build_read_gmail_tool(api_public_url=api_public_url),
                build_gmail_confirm_send_tool(api_public_url=api_public_url),
                build_gmail_cancel_send_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras enviar, cancelar o borrador expirado."
                    ),
                },
            ],
        },
        {
            "name": STATE_PUBLISH_CONFIRM_PENDING,
            "state_prompt": PUBLISH_CONFIRM_STATE_PROMPT,
            "tools": [
                build_check_meta_networks_tool(api_public_url=api_public_url),
                build_meta_confirm_publish_tool(api_public_url=api_public_url),
                build_meta_cancel_publish_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras publicar, cancelar o borrador expirado."
                    ),
                },
            ],
        },
'''
    if gmail_state_end not in text:
        raise SystemExit("gmail confirm state block not found")
    text = text.replace(gmail_state_end, publish_state, 1)

# --- Metrics ---
if '"search_web": _stats("search_web")' in text and '"meta_prepare_publish"' not in text:
    text = text.replace(
        '"search_web": _stats("search_web"),\n',
        '"search_web": _stats("search_web"),\n'
        '        "meta_prepare_publish": _stats("meta_prepare_publish"),\n'
        '        "meta_confirm_publish": _stats("meta_confirm_publish"),\n'
        '        "meta_cancel_publish": _stats("meta_cancel_publish"),\n'
        '        "check_meta_networks": _stats("check_meta_networks"),\n',
        1,
    )

# --- Executors before resolve_environment_tool_query ---
if "async def execute_search_web_tool" in text and "async def execute_meta_prepare_publish_tool" not in text:
    text = text.replace(
        "# Compat tests / imports previos\nresolve_environment_tool_query = resolve_tool_query\n",
        '''
def _run_meta_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.meta_publish_flow import prepare_meta_publish

    query = resolve_tool_query(payload, args)
    return prepare_meta_publish(
        user_id,
        call_id=call_id,
        platform=str(args.get("platform") or ""),
        caption=str(args.get("caption") or ""),
        query=query,
    )


def _run_meta_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.meta_publish_flow import confirm_meta_publish

    return confirm_meta_publish(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_meta_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.meta_publish_flow import cancel_meta_publish

    return cancel_meta_publish(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_meta_prepare_publish_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="meta_prepare_publish",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_meta_prepare,
    )


async def execute_meta_confirm_publish_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="meta_confirm_publish",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_meta_confirm,
    )


async def execute_meta_cancel_publish_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="meta_cancel_publish",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_meta_cancel,
    )


async def execute_check_meta_networks_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.services.voice_tool_executor import execute_voice_tool

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(call_id=call_id, tool_name="check_meta_networks", latency_ms=latency_ms, ok=False)
        return {"result": "No identifiqué al usuario, señor.", "latency_ms": latency_ms, "ok": False}
    result = await execute_voice_tool("consultar_redes_conectadas", user_id, {})
    spoken = str(result.get("spoken") or "").strip() or "No pude consultar sus redes, señor."
    ok = bool(result.get("ok", True))
    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(call_id=call_id, tool_name="check_meta_networks", latency_ms=latency_ms, ok=ok)
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


# Compat tests / imports previos
resolve_environment_tool_query = resolve_tool_query
''',
        1,
    )

PATH.write_text(text, encoding="utf-8")
print("meta patch ok")
