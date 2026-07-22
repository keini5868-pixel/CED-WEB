"""Plugin FitLine / PM International — contenido curado + anclas de búsqueda.

Tono UI (excepto Limitaciones/riesgos): red de franquicias, equipo de crecimiento,
socios de negocio, ingresos residuales. Sin "MLM"/"afiliados"/"multinivel" en copy
visible de secciones 1–6.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

OPPORTUNITY_ID = "fitline_pm"

# Soft-tone curated body (sections 1–6). Risks are honest (section 7).
_CURATED_AS_OF = "2026-07-22"


def _sponsorship_url() -> str:
    return (get_settings().opportunities_fitline_sponsor_url or "").strip()


def fitline_pm_plugin() -> dict[str, Any]:
    sponsor = _sponsorship_url()
    return {
        "id": OPPORTUNITY_ID,
        "title": "PM International / FitLine",
        "tagline": (
            "Negocio de productos de nutrición y bienestar con red de franquicias "
            "e ingresos residuales."
        ),
        "category": "direct_sales_network",
        "status": "available",
        "search_anchors": [
            "PM International FitLine",
            "FitLine business opportunity",
            "PM International FitLine manager package",
        ],
        "sponsorship": {
            "url": sponsor,
            "cta_label": "Activar su negocio (paquete manager)",
            "configured": bool(sponsor),
        },
        "curated": {
            "as_of": _CURATED_AS_OF,
            "sources": [
                {
                    "title": "PM-International (sitio oficial)",
                    "url": "https://www.pm-international.com/",
                },
                {
                    "title": "FitLine (marca de productos)",
                    "url": "https://www.fitline.com/",
                },
            ],
            "sections": {
                "what_is": {
                    "attribution": "curated",
                    "body": (
                        "PM International es la empresa detrás de FitLine, una línea de "
                        "productos de nutrición y bienestar. Quienes activan su negocio "
                        "pueden comercializar productos de calidad y construir un equipo "
                        "de crecimiento (red de franquicias) con posibilidad de ingresos "
                        "residuales, además de la venta directa de producto.\n\n"
                        "CED es la herramienta de estrategia y desarrollo de habilidades "
                        "para hacer crecer este negocio (análisis de viabilidad, "
                        "tendencias y apoyo operativo)."
                    ),
                },
                "how_it_works": {
                    "attribution": "curated",
                    "body": (
                        "El modelo combina:\n"
                        "• Venta de productos FitLine a clientes finales.\n"
                        "• Construcción de un equipo de crecimiento / socios de negocio "
                        "en una red de franquicias.\n"
                        "• Ingresos residuales ligados al volumen y desarrollo del "
                        "equipo, según el plan de compensación publicado por la empresa "
                        "(verifique siempre la documentación oficial vigente).\n\n"
                        "CED acompaña con estrategia: no sustituye la información oficial "
                        "de PM International ni garantiza resultados."
                    ),
                },
                "requirements": {
                    "attribution": "curated",
                    "body": (
                        "Para iniciar su franquicia / activar su negocio suele requerirse:\n"
                        "• Registro a través de un patrocinador (enlace de activación).\n"
                        "• Adquisición del paquete de inicio correspondiente (p. ej. "
                        "paquete manager), según las condiciones oficiales vigentes.\n"
                        "• Cumplir políticas de la empresa y de su país (edad, "
                        "residencia, uso correcto de marca).\n\n"
                        "Los requisitos exactos y precios del paquete pueden cambiar: "
                        "confirme en fuentes oficiales o vía su enlace de activación. "
                        "CED no inventa cifras de inscripción."
                    ),
                },
                "income_potential": {
                    "attribution": "curated",
                    "body": (
                        "El potencial de ingreso depende de ventas de producto, "
                        "consistencia y desarrollo del equipo de crecimiento. "
                        "Puede incluir márgenes por venta e ingresos residuales "
                        "según el plan oficial.\n\n"
                        "CED no publica montos de comisión ni promesas de ingreso "
                        "sin una fuente verificable de esta sesión. Si la búsqueda "
                        "no aporta cifras atribuibles, se marca como limitación de "
                        "datos — nunca como proyección inventada."
                    ),
                },
                "getting_started": {
                    "attribution": "curated",
                    "body": (
                        "Pasos sugeridos para activar su negocio:\n"
                        "1. Revisar productos FitLine y el modelo de ingresos residuales "
                        "en materiales oficiales.\n"
                        "2. Usar el enlace de patrocinio (sección Afiliación) para "
                        "registrarse al paquete manager con su patrocinador.\n"
                        "3. Completar el programa de mentoría y desarrollo empresarial "
                        "con el equipo especializado asociado a ese enlace.\n"
                        "4. Usar CED (Viabilidad, Tendencias, Oportunidades) como "
                        "herramienta de estrategia y habilidades para crecer.\n"
                        "5. Cumplir siempre las políticas de marca y publicidad de "
                        "PM International."
                    ),
                },
                "affiliation": {
                    "attribution": "curated",
                    "body": (
                        "Quienes se registren a través del enlace personal de patrocinio "
                        "de este módulo obtienen acceso a mentoría directa y "
                        "acompañamiento estratégico de un equipo especializado "
                        "(programa de mentoría y desarrollo empresarial).\n\n"
                        "CED es la herramienta de estrategia y desarrollo de habilidades "
                        "para hacer crecer este negocio una vez activado.\n\n"
                        "Use el botón «Activar su negocio (paquete manager)» para abrir "
                        "el enlace de registro. Si el enlace aún no está configurado en "
                        "el servidor, aparecerá un aviso en esta ficha."
                    ),
                },
                "risks": {
                    "attribution": "curated",
                    "body": (
                        "Limitaciones y riesgos (información explícita del modelo real):\n"
                        "• Se trata de un modelo de venta directa con estructura de "
                        "comisiones por red: los ingresos suelen depender tanto de "
                        "ventas personales como del volumen generado por la red.\n"
                        "• El ingreso no está garantizado. Muchas personas obtienen "
                        "resultados bajos o nulos si no hay ventas consistentes ni "
                        "desarrollo de red.\n"
                        "• Puede haber costo de paquete de inicio / inventario; evalúe "
                        "si encaja con su presupuesto antes de activar el negocio.\n"
                        "• Está sujeto a regulaciones locales sobre venta directa y "
                        "publicidad de ingresos; no haga afirmaciones engañosas.\n"
                        "• CED no es un patrocinador oficial de PM International ni "
                        "garantiza aceptación, rangos o comisiones."
                    ),
                },
            },
        },
    }
