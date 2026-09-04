"""Motor de misión cognitiva para WhatsApp — no es un árbol de nodos.

El objetivo lo fija el dueño (directriz). Cada contacto tiene ADN (tono),
puntuación de cierre y riesgo de fuga. La IA persigue el objetivo según
ese perfil, no según una burbuja rígida.
"""

from __future__ import annotations

import re
from typing import Any

DNA_LABELS = ("Urgente", "Analítico", "Escéptico", "Decidido")

_URGENTE = re.compile(
    r"\b(urgente|ya|ahora|hoy|inmediato|inmediata|rápido|rapido|"
    r"cuanto sale|cuánto sale|lo necesito|esta semana)\b",
    re.I,
)
_ANALITICO = re.compile(
    r"\b(cómo funciona|como funciona|detalle|detalles|diferencia|compar|"
    r"por qué|porque|garantía|garantia|estudio|prueba|evidencia|explic)\b",
    re.I,
)
_ESCEPTICO = re.compile(
    r"\b(estafa|no creo|mentira|ya me dijeron|no funciona|caro|"
    r"desconfío|desconfio|engaño|engano|duda|sospech)\b",
    re.I,
)
_DECIDIDO = re.compile(
    r"\b(lo quiero|listo|cómo pago|como pago|transferencia|cuenta|"
    r"sí quiero|si quiero|agendemos|confirmo|pásame el|pasame el|"
    r"pago ahora|comprar)\b",
    re.I,
)
_PAGO = re.compile(
    r"\b(pago|pagué|pague|comprobante|transfer|voucher|recibo|"
    r"depósito|deposito|zelle|paypal)\b",
    re.I,
)
_FUGA = re.compile(
    r"\b(no gracias|después|despues|ahora no|no me interesa|"
    r"déjame|dejame|otro día|otro dia)\b",
    re.I,
)
_NEG = re.compile(r"\b(malo|pésimo|pesimo|estafa|molesto|enoja|horrible)\b", re.I)
_POS = re.compile(r"\b(gracias|excelente|perfecto|genial|me encanta)\b", re.I)


def classify_prospect_dna(text: str, *, previous: str = "") -> str:
    t = (text or "").strip()
    scores = {
        "Urgente": len(_URGENTE.findall(t)),
        "Analítico": len(_ANALITICO.findall(t)),
        "Escéptico": len(_ESCEPTICO.findall(t)),
        "Decidido": len(_DECIDIDO.findall(t)),
    }
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        prev = (previous or "").strip()
        return prev if prev in DNA_LABELS else "Analítico"
    return best


def classify_sentiment(text: str) -> str:
    t = text or ""
    if _NEG.search(t) or _ESCEPTICO.search(t):
        return "negativo"
    if _POS.search(t):
        return "positivo"
    return "neutro"


def score_close_probability(
    text: str,
    *,
    dna: str,
    previous_score: int = 0,
    has_image: bool = False,
) -> int:
    t = text or ""
    raw = 18
    if dna == "Decidido":
        raw += 42
    elif dna == "Urgente":
        raw += 22
    elif dna == "Escéptico":
        raw -= 12
    if _PAGO.search(t):
        raw += 28
    if has_image and _PAGO.search(t):
        raw += 12
    if _FUGA.search(t):
        raw -= 25
    raw = max(5, min(97, raw))
    prev = max(0, min(100, int(previous_score or 0)))
    blended = int(round(0.55 * prev + 0.45 * raw)) if prev else raw
    return max(5, min(97, blended))


def score_leak_risk(text: str, *, dna: str, opted_out: bool = False) -> int:
    if opted_out:
        return 95
    t = text or ""
    risk = 12
    if _FUGA.search(t):
        risk += 50
    if dna == "Escéptico":
        risk += 22
    if classify_sentiment(t) == "negativo":
        risk += 18
    return max(5, min(95, risk))


def needs_human_handoff(
    *,
    close_score: int,
    leak_risk: int,
    dna: str,
    sentiment: str,
    has_image: bool,
    text: str,
) -> str:
    """Razón corta o vacío si la IA puede seguir sola."""
    if close_score >= 85:
        return "cierre"
    if has_image and _PAGO.search(text or ""):
        return "comprobante"
    if dna == "Escéptico" and (sentiment == "negativo" or leak_risk >= 55):
        return "duda_critica"
    if leak_risk >= 70:
        return "fuga"
    return ""


def mission_overlay(
    *,
    dna: str,
    sentiment: str,
    close_score: int,
    leak_risk: int,
    human: str,
    has_image: bool,
) -> str:
    lines = [
        "Misión cognitiva (no sigas un guion lineal de nodos): persigue el objetivo "
        "del dueño según el perfil de ESTA persona.",
        f"ADN del prospecto: {dna}. Tono: {sentiment}.",
        f"Probabilidad de cierre estimada: {close_score}%. Riesgo de fuga: {leak_risk}%.",
    ]
    if dna == "Urgente":
        lines.append("Estilo: directo, concreto, un solo siguiente paso inmediato.")
    elif dna == "Analítico":
        lines.append("Estilo: datos claros, sin presión; una explicación breve y una pregunta.")
    elif dna == "Escéptico":
        lines.append("Estilo: no discutas; reconoce la duda, da un hecho verificable, no vendas agresivo.")
    else:
        lines.append("Estilo: confirma lo que quiere y facilita el cierre (pago, agenda o enlace).")
    if has_image:
        lines.append(
            "El contacto envió una imagen o captura. Responde a lo que se VE "
            "(pago, error, registro, producto). No inventes montos ni estados."
        )
    if human == "cierre":
        lines.append(
            "Alerta de intervención: cierre alto. Facilita el paso final y deja "
            "espacio a que un humano tome el chat si hace falta."
        )
    elif human == "comprobante":
        lines.append("Alerta: posible comprobante. Confirma lo visible y avisa que un humano puede validar el pago.")
    elif human:
        lines.append("Alerta: duda o fuga. Prioriza retener con claridad, no con un discurso largo.")
    return "\n".join(lines)


def analyze_turn(
    text: str,
    *,
    previous_dna: str = "",
    previous_close: int = 0,
    opted_out: bool = False,
    has_image: bool = False,
) -> dict[str, Any]:
    dna = classify_prospect_dna(text, previous=previous_dna)
    sentiment = classify_sentiment(text)
    close_score = score_close_probability(
        text, dna=dna, previous_score=previous_close, has_image=has_image
    )
    leak_risk = score_leak_risk(text, dna=dna, opted_out=opted_out)
    human = needs_human_handoff(
        close_score=close_score,
        leak_risk=leak_risk,
        dna=dna,
        sentiment=sentiment,
        has_image=has_image,
        text=text,
    )
    return {
        "prospect_dna": dna,
        "sentiment": sentiment,
        "close_score": close_score,
        "leak_risk": leak_risk,
        "human_alert": human,
        "overlay": mission_overlay(
            dna=dna,
            sentiment=sentiment,
            close_score=close_score,
            leak_risk=leak_risk,
            human=human,
            has_image=has_image,
        ),
    }
