"""Tests — módulo ambiente (Weather, Air Quality, Solar, Pollen)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.environment_module import (
    get_air_quality,
    get_pollen,
    get_solar,
    get_weather,
    handle_environment_query,
    handle_environment_query_sync,
    is_environment_intent,
)
from app.services.ced_orchestrator import detect_module, detect_module_from_patterns


def test_is_environment_intent():
    assert is_environment_intent("¿qué clima hay hoy?")
    assert is_environment_intent("¿cómo está la calidad del aire?")
    assert is_environment_intent("¿hay mucho polen hoy?")
    assert not is_environment_intent("hola")


def test_orchestrator_detects_environment_module():
    assert detect_module_from_patterns("¿qué clima hay hoy?") == "environment"
    mod = detect_module("¿cómo está la calidad del aire?", [])
    assert mod == "environment"


def test_get_weather_parses_google_response():
    async def run() -> str:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "temperature": {"degrees": 28, "unit": "CELSIUS"},
            "weatherCondition": {
                "description": {"text": "Cielo despejado", "languageCode": "es"},
                "type": "CLEAR",
            },
            "relativeHumidity": 65,
            "wind": {"speed": {"value": 12, "unit": "KILOMETERS_PER_HOUR"}},
        }
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.modules.environment_module._google_maps_key",
            return_value="test-key",
        ):
            with patch("app.modules.environment_module.httpx.AsyncClient", return_value=mock_client):
                result = await get_weather(35.22, -80.84)
        return result["spoken"]

    spoken = asyncio.run(run())
    assert "28 grados" in spoken
    assert "cielo despejado" in spoken
    assert "65%" in spoken
    assert "12" in spoken


def test_get_air_quality_parses_google_response():
    async def run() -> str:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "indexes": [{"category": "Buena", "aqiDisplay": 42}],
        }
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.modules.environment_module._google_maps_key",
            return_value="test-key",
        ):
            with patch("app.modules.environment_module.httpx.AsyncClient", return_value=mock_client):
                result = await get_air_quality(35.22, -80.84)
        return result["spoken"]

    spoken = asyncio.run(run())
    assert "Buena" in spoken
    assert "42" in spoken


def test_get_pollen_parses_google_response():
    async def run() -> str:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "dailyInfo": [
                {
                    "pollenTypeInfo": [
                        {
                            "displayName": "Árbol",
                            "indexInfo": {"category": "Bajo"},
                        },
                        {
                            "displayName": "Pasto",
                            "indexInfo": {"category": "Moderado"},
                        },
                    ]
                }
            ]
        }
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.modules.environment_module._google_maps_key",
            return_value="test-key",
        ):
            with patch("app.modules.environment_module.httpx.AsyncClient", return_value=mock_client):
                result = await get_pollen(35.22, -80.84)
        return result["spoken"]

    spoken = asyncio.run(run())
    assert "Árbol: Bajo" in spoken
    assert "Pasto: Moderado" in spoken


def test_get_solar_parses_google_response():
    async def run() -> str:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "solarPotential": {"maxSunshineHoursPerYear": 1898},
        }
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.modules.environment_module._google_maps_key",
            return_value="test-key",
        ):
            with patch("app.modules.environment_module.httpx.AsyncClient", return_value=mock_client):
                result = await get_solar(35.22, -80.84)
        return result["spoken"]

    spoken = asyncio.run(run())
    assert "5.2 horas de sol promedio hoy" in spoken


def test_handle_environment_query_general_clima():
    async def run() -> str:
        with patch(
            "app.modules.environment_module.get_weather",
            AsyncMock(return_value={"spoken": "28 grados, cielo despejado, humedad 65%, viento 12 km/h"}),
        ):
            with patch(
                "app.modules.environment_module.get_air_quality",
                AsyncMock(return_value={"spoken": "Calidad del aire Buena, índice 42"}),
            ):
                result = await handle_environment_query("¿qué clima hay hoy?", 35.22, -80.84)
        return result["spoken"]

    spoken = asyncio.run(run())
    assert spoken.startswith("Señor,")
    assert "28 grados" in spoken


def test_handle_environment_query_outdoor_work():
    async def run() -> str:
        with patch(
            "app.modules.environment_module.get_weather",
            AsyncMock(return_value={"spoken": "26 grados, cielo despejado, humedad 60%, viento 10 km/h"}),
        ):
            with patch(
                "app.modules.environment_module.get_air_quality",
                AsyncMock(return_value={"spoken": "Calidad del aire Buena, índice 42"}),
            ):
                with patch(
                    "app.modules.environment_module.get_solar",
                    AsyncMock(return_value={"spoken": "5.2 horas de sol promedio hoy"}),
                ):
                    result = await handle_environment_query(
                        "¿es buen día para trabajar afuera?",
                        35.22,
                        -80.84,
                    )
        return result["spoken"]

    spoken = asyncio.run(run())
    assert "26 grados" in spoken
    assert "5.2 horas de sol promedio hoy" in spoken
    assert "Calidad del aire Buena" in spoken
    assert "Excelente día para trabajar al exterior" in spoken


def test_handle_environment_query_sync_uses_location():
    with patch(
        "app.modules.environment_module.resolve_environment_coordinates",
        return_value=(35.22, -80.84),
    ):
        with patch(
            "app.modules.environment_module.handle_environment_query",
            AsyncMock(return_value={"spoken": "Señor, 28 grados, despejado."}),
        ):
            result = handle_environment_query_sync("user-1", "¿qué clima hay hoy?")
    assert "28 grados" in result["spoken"]
