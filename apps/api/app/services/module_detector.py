"""Detección de intención por módulo — núcleo v2 (voz primero).

Dos etapas, diseñadas para MATAR falsos positivos sin penalizar la latencia del
chat base:

  Etapa 1 — señal estricta (0 latencia, sin LLM):
    Cada módulo declara anchors EXIGENTES (frases ancla multi-palabra o verbos de
    acción claros), no palabras sueltas. Se separan en:
      - STRICT_ANCHORS: intención inequívoca de acción → activa directo.
      - SOFT_ANCHORS: menciona el tema pero PODRÍA ser conversación casual →
        requiere Etapa 2 para confirmar.

  Etapa 2 — clasificador LLM ligero (solo si hay candidato ambiguo):
    Una llamada minúscula al modelo que responde ACCION vs CASUAL. Solo corre
    cuando la Etapa 1 marcó un SOFT candidate. Así los turnos que claramente no
    son de módulo (o que son claramente de acción) nunca pagan la latencia.

Este módulo es autónomo y testeable en aislamiento: `detect_intent` acepta un
`classify` inyectable para las pruebas (sin red).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# Confianza de la detección.
CONF_NONE = "none"      # sin señal → conversación base
CONF_ANCHOR = "anchor"  # ancla estricta → acción inequívoca
CONF_LLM = "llm"        # confirmada por clasificador de intención
CONF_SOFT = "soft"      # candidato ambiguo sin resolver (no se corrió Etapa 2)


@dataclass(frozen=True)
class Detection:
    """Resultado de la detección de intención."""

    module: str | None
    confidence: str
    is_action: bool
    matched: str | None = None

    @property
    def activate(self) -> bool:
        """¿Debe el orquestador activar un módulo con este resultado?"""
        return bool(self.module) and self.is_action


# Orden de prioridad al escanear (resuelve solapamientos, ej. PDF gana sobre
# la mención "finanzas" en "hazme un pdf de finanzas"). Los módulos de acción
# explícita van primero; los de datos/tema van después.
MODULE_PRIORITY: tuple[str, ...] = (
    "camera",
    "map",
    "pdf",
    "image_gen",
    "social",
    "prospection",
    "gmail",
    "calendar",
    "stripe",
    "finance",
    "weather",
    "pollen",
    "air_quality",
    "datetime",
    "web_search",
    "memory",
)

# Etiqueta legible por módulo — usada en el prompt del clasificador (Etapa 2).
MODULE_LABELS: dict[str, str] = {
    "camera": "cámara y visión (mirar/analizar lo que ve la cámara)",
    "map": "navegación / Google Maps (llevar a un destino, calcular ruta)",
    "pdf": "generar un documento PDF",
    "image_gen": "generar/crear una imagen",
    "social": "publicar en redes sociales (Instagram/Facebook)",
    "prospection": "prospección / búsqueda de prospectos",
    "gmail": "leer o enviar correos (Gmail)",
    "calendar": "calendario y eventos (agenda, citas)",
    "stripe": "suscripción y pagos (plan, facturación)",
    "finance": "finanzas personales (gastos, ingresos, ahorro, pagos)",
    "weather": "clima / pronóstico del tiempo",
    "pollen": "índice de polen",
    "air_quality": "calidad del aire",
    "datetime": "hora o fecha actual",
    "web_search": "buscar información actual en internet",
    "memory": "recordar algo dicho antes o guardar un recordatorio",
}

# ---------------------------------------------------------------------------
# Anchors estrictos — intención de acción inequívoca (activan sin LLM).
# Multi-palabra o verbo de acción + objeto. NUNCA palabras sueltas.
# ---------------------------------------------------------------------------
STRICT_ANCHORS: dict[str, tuple[str, ...]] = {
    "camera": (
        r"\babre\s+(?:la\s+)?c[áa]mara\b",
        r"\benciende\s+(?:la\s+)?c[áa]mara\b",
        r"\bactiva\s+(?:la\s+)?c[áa]mara\b",
        r"\banaliza\s+esto\b",
        r"\bmira\s+esto\b",
        r"\bqu[ée]\s+ves\b",
        r"\bdescribe\s+lo\s+que\s+ves\b",
    ),
    "map": (
        r"\bll[ée]vame\s+a\b",
        r"\bnav[ée]ga(?:me)?\s+a\b",
        r"\bnavegaci[óo]n\s+a\b",
        r"\bruta\s+(?:a|hacia|hasta)\b",
        r"\bc[óo]mo\s+llego\s+a\b",
        r"\bind[íi]came\s+c[óo]mo\s+llegar\b",
        r"\babre\s+(?:el\s+)?mapa\b",
        r"\bmodo\s+conduc(?:ir|ci[óo]n)\b",
    ),
    "pdf": (
        r"\b(?:haz(?:me)?|genera(?:r|me)?|crea(?:r|me)?|exporta(?:r)?)\s+(?:un\s+)?pdf\b",
        r"\bpdf\s+(?:de|con|sobre)\b",
        r"\bdocumento\s+pdf\b",
        r"\breporte\s+en\s+pdf\b",
    ),
    "image_gen": (
        r"\b(?:g[ée]n[ée]ra(?:r|me)?|cr[ée]a(?:r|me)?|haz(?:me)?|dis[ée][ñn]a(?:r|me)?|dibuja(?:r|me)?|pinta(?:r|me)?)\s+(?:una?\s+)?(?:imagen|foto|ilustraci[óo]n|logo|banner|flyer|dise[ñn]o|arte|portada)\b",
    ),
    "social": (
        r"\bpubl[íi]c(?:ame|a)\s+esto\b",
        r"\bhaz\s+la\s+publicaci[óo]n\b",
        r"\bpubl[íi]ca(?:lo|la)?\b",
        r"\bpublicar\b",
        r"\bpost[ée]a(?:lo|la)?\b",
        r"\bsube\s+a\s+(?:instagram|facebook)\b",
        r"\bcomparte\s+en\s+(?:instagram|facebook|redes)\b",
    ),
    "prospection": (
        r"\b(?:activa|desactiva)\s+(?:la\s+)?prospecci[óo]n\b",
        r"\bmodo\s+prospecci[óo]n\b",
        r"\breporte\s+de\s+prospecci[óo]n\b",
        r"\bbuscar?\s+prospectos?\b",
    ),
    "gmail": (
        r"\bleer\s+mis\s+correos\b",
        r"\bl[ée]e(?:me)?\s+el\s+correo\s+de\b",
        r"\bl[ée]e(?:me)?\s+(?:el\s+|mi\s+|los\s+|mis\s+)?(?:correos?|emails?|gmail)\b",
        r"\benv[íi]a(?:me)?\s+(?:un\s+)?(?:correo|email)\b",
        r"\brev[íi]sa\s+(?:mi\s+)?(?:correo|gmail|bandeja)\b",
        r"\bcorreos?\s+(?:importantes?|nuevos?|sin\s+leer)\b",
    ),
    "calendar": (
        r"\bqu[ée]\s+tengo\s+(?:hoy|ma[ñn]ana|esta\s+semana|programado|agendado)\b",
        r"\bag[ée]nda(?:me|r)?\b",
        r"\bprograma(?:me|r)?\s+(?:una\s+)?(?:cita|reuni[óo]n|evento)\b",
        r"\bmi\s+calendario\b",
        r"\bqu[ée]\s+eventos\s+tengo\b",
        r"\bqu[ée]\s+hay\s+en\s+(?:mi\s+)?(?:agenda|calendario)\b",
    ),
    "stripe": (
        r"\bmi\s+suscripci[óo]n\b",
        r"\bcancela(?:r)?\s+(?:mi\s+)?suscripci[óo]n\b",
        r"\bm[ée]todo\s+de\s+pago\b",
        r"\bactualiza(?:r)?\s+(?:mi\s+)?(?:plan|tarjeta|m[ée]todo\s+de\s+pago)\b",
        r"\bmejora(?:r)?\s+(?:mi\s+)?plan\b",
    ),
    "finance": (
        r"\bc[óo]mo\s+van\s+mis\s+finanzas\b",
        r"\bresumen\s+de\s+(?:mis\s+)?finanzas\b",
        r"\bcu[áa]nto\s+(?:he\s+)?gast[éeè]\b",
        r"\b(?:tengo|debo|hay)\s+que\s+pagar\b",
        r"\bpagos?\s+pendientes?\b",
        r"\bgast[ée]\s+\d",
        r"\b(?:recib[íi]|gan[ée]|cobr[ée]|me\s+pagaron)\s+\d",
        r"\bregistra(?:r|me)?\s+(?:un\s+)?(?:gasto|ingreso)\b",
        r"\bgu[áa]rdame\s+que\b",
        # Frases explícitas "... en finanzas ..." (guardar/anotar/registrar).
        r"\b(?:gu[áa]rdame|an[óo]tame|anota(?:me)?|reg[íi]strame|registra|ap[úu]ntame|apunta)\s+en\s+finanzas\b",
        r"\ben\s+finanzas\s+que\b",
        # Tolerancia a errores de STT: "guárdame en finanzas" suena como
        # "soy guardian finanzas" / "guardián finanzas". Contiene "finanzas"
        # explícito, así que es seguro tratarlo como intención de acción.
        r"\bguard[ií][aá]n\s+(?:en\s+|de\s+)?finanzas\b",
        r"\bguardi[aá]n\s+finanzas\b",
        r"\bplan\s+de\s+ahorro\b",
        r"\bc[óo]mo\s+voy\b.*\b(?:mes|finanzas|dinero)\b",
        r"\bcu[áa]nto\s+debo\b",
    ),
    "weather": (
        r"\b(?:c[óo]mo|qu[ée])\s+(?:va\s+a\s+estar|estar[áa]|est[áa])\s+el\s+(?:clima|tiempo)\b",
        r"\bpron[óo]stico\s+(?:del?\s+)?(?:clima|tiempo|d[íi]a)\b",
        r"\bva\s+a\s+llover\b",
        r"\b(?:clima|tiempo)\s+(?:hoy|ma[ñn]ana|de\s+hoy|para\s+hoy)\b",
        r"\bqu[ée]\s+clima\s+(?:hace|hay|har[áa])\b",
    ),
    "pollen": (
        r"\b[íi]ndice\s+de\s+polen\b",
        r"\bnivel(?:es)?\s+de\s+polen\b",
        r"\bc[óo]mo\s+est[áa]\s+el\s+polen\b",
    ),
    "air_quality": (
        r"\bcalidad\s+del\s+aire\b",
        r"\b[íi]ndice\s+de\s+(?:calidad\s+del\s+)?aire\b",
        r"\bcontaminaci[óo]n\s+del?\s+aire\b",
    ),
    "datetime": (
        r"\bqu[ée]\s+hora\s+es\b",
        r"\bqu[ée]\s+d[íi]a\s+(?:es|estamos)\b",
        r"\bqu[ée]\s+fecha\s+es\b",
        r"\ben\s+qu[ée]\s+fecha\s+estamos\b",
    ),
    "web_search": (
        r"\bbusca\s+en\s+internet\b",
        r"\b[úu]ltimas\s+noticias\b",
        r"\bnoticias\s+(?:de|sobre)\b",
        r"\bbusca\s+informaci[óo]n\s+(?:de|sobre)\b",
        r"\bqu[ée]\s+pas[óo]\s+con\b",
    ),
    "memory": (
        r"\brecuerdas?\s+(?:lo\s+que|cuando|que|si)\b",
        r"\bqu[ée]\s+hablamos\s+(?:de|sobre|ayer|antes)\b",
        r"\bgu[áa]rdame\s+que\b",
        r"\brecu[ée]rdame\s+que\b",
        r"\banota\s+que\b",
    ),
}

# ---------------------------------------------------------------------------
# Anchors suaves — el tema aparece pero PODRÍA ser casual. Requieren Etapa 2.
# Ej: "mi situación financiera está difícil" (casual) vs
#     "dame un resumen de finanzas" (acción → ya cubierto por STRICT).
# ---------------------------------------------------------------------------
SOFT_ANCHORS: dict[str, tuple[str, ...]] = {
    "finance": (
        r"\bfinan(?:zas|ciera|ciero)\b",
        r"\bmis\s+(?:gastos|ingresos|deudas|ahorros)\b",
    ),
    "map": (
        r"\bd[óo]nde\s+queda\b",
        r"\bd[óo]nde\s+hay\s+un\b",
        r"\bc[óo]mo\s+llegar\b",
    ),
    "weather": (
        r"\bclima\b",
        r"\btemperatura\b",
        r"\bva\s+a\s+llover\b",
        r"\bhace\s+(?:calor|fr[íi]o)\b",
    ),
    "pollen": (
        r"\bpolen\b",
        r"\balergias?\b",
    ),
    "air_quality": (
        r"\baire\s+(?:hoy|ahora|contaminado)\b",
    ),
    "gmail": (
        r"\b(?:correo|email|gmail|bandeja)\b",
    ),
    "calendar": (
        r"\b(?:evento|cita|reuni[óo]n|agenda)\b",
    ),
    "social": (
        r"\bredes\s+sociales\b",
        r"\b(?:instagram|facebook)\b",
    ),
    "prospection": (
        r"\bprospecci[óo]n\b",
        r"\bprospectos?\b",
    ),
    "stripe": (
        r"\bsuscripci[óo]n\b",
        r"\bfacturaci[óo]n\b",
        r"\bplan\s+(?:premium|pro|pago)\b",
    ),
    "web_search": (
        r"\bnoticias\b",
    ),
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _first_anchor_match(text: str, table: dict[str, tuple[str, ...]]) -> tuple[str, str] | None:
    """Devuelve (módulo, patrón) del primer match por orden de prioridad."""
    for module in MODULE_PRIORITY:
        for pattern in table.get(module, ()):
            if re.search(pattern, text):
                return module, pattern
    return None


# Firma del clasificador de Etapa 2: (texto, módulo_candidato) -> es_acción.
IntentClassifier = Callable[[str, str], bool]


def _llm_classify_intent(text: str, module: str) -> bool:
    """Clasificador de intención por defecto (Gemini Flash, mínimo y con timeout).

    Devuelve True si el usuario realmente pide ACTIVAR la función; False si solo
    la mencionó de forma casual. Ante cualquier error, devuelve False para NO
    generar falsos positivos (la premisa del rediseño).
    """
    label = MODULE_LABELS.get(module, module)
    try:
        from app.config import get_settings

        settings = get_settings()
        api_key = settings.google_api_key.strip()
        if not api_key:
            return False

        from google import genai
        from google.genai import types

        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=6000),
            )
        except Exception:  # noqa: BLE001
            client = genai.Client(api_key=api_key)

        prompt = (
            "Eres un clasificador de intención para un asistente de voz.\n"
            f'El usuario dijo: "{text}".\n'
            f"¿El usuario está pidiendo ACTIVAR/usar la función de {label}, "
            "o solo la mencionó de forma casual en la conversación?\n"
            'Responde SOLO con una palabra: "ACCION" o "CASUAL".'
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=8,
            ),
        )
        answer = (getattr(response, "text", "") or "").strip().upper()
        return "ACCION" in answer or "ACCIÓN" in answer
    except Exception as exc:  # noqa: BLE001
        logger.warning("[DETECT] clasificador de intención falló module=%s: %s", module, exc)
        return False


def detect_intent(
    user_text: str,
    *,
    classify: IntentClassifier | None = _llm_classify_intent,
    run_stage2: bool = True,
) -> Detection:
    """Detecta la intención de módulo del turno.

    Args:
        user_text: texto del usuario.
        classify: clasificador de Etapa 2 (inyectable para tests). Si es None,
            los candidatos suaves se devuelven sin resolver (confidence=CONF_SOFT).
        run_stage2: si False, nunca corre Etapa 2 (útil para tests puros de
            anchors o para un modo "solo estricto").

    Returns:
        Detection. Usa `.activate` para saber si el orquestador debe activar.
    """
    text = _normalize(user_text)
    if not text:
        return Detection(module=None, confidence=CONF_NONE, is_action=False)

    # Etapa 1a — ancla estricta → acción inequívoca.
    strict = _first_anchor_match(text, STRICT_ANCHORS)
    if strict:
        module, pattern = strict
        return Detection(
            module=module,
            confidence=CONF_ANCHOR,
            is_action=True,
            matched=pattern,
        )

    # Etapa 1b — ancla suave → candidato ambiguo.
    soft = _first_anchor_match(text, SOFT_ANCHORS)
    if not soft:
        return Detection(module=None, confidence=CONF_NONE, is_action=False)

    module, pattern = soft
    if not run_stage2 or classify is None:
        # No se resuelve: el caller decide (o modo solo-estricto).
        return Detection(
            module=module,
            confidence=CONF_SOFT,
            is_action=False,
            matched=pattern,
        )

    # Etapa 2 — clasificador LLM ligero.
    is_action = bool(classify(user_text, module))
    return Detection(
        module=module,
        confidence=CONF_LLM,
        is_action=is_action,
        matched=pattern,
    )
