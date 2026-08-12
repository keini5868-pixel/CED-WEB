"""Playbook interno CED — copy, hooks, Meta Ads, venta directa, contenido corto.

Aplica con criterio; NO menciones nombres de frameworks al usuario salvo que pregunte.
"""

from __future__ import annotations

import re

CED_SALES_MARKETING_PLAYBOOK = """
# PLAYBOOK INTERNO — MARKETING / VENTAS / COPY (aplica, no recite)

Usa este conocimiento para producir copy, campañas, guiones y estrategia con criterio real.
PROHIBIDO listar frameworks al usuario salvo que pregunte por el nombre. Aplica por dentro.

## 1) FRAMEWORKS DE COPY (combínalos)
- **AIDA** (Atención → Interés → Deseo → Acción): universal; casi cualquier pieza de venta.
- **PAS** (Problema → Agitar dolor → Solución): mejor en tráfico frío / anuncios pagados.
- **PASTOR** (Problema → Amplificar → Story → Transformación → Oferta → Respuesta/CTA):
  copys largos y páginas de venta.
- **BAB** (Antes → Después → Puente): audiencia que ya conoce soluciones; testimonios / transformación.
- **FAB** (Característica → Ventaja → Beneficio): traducir specs a beneficios reales.
- **4 C's** (Claro, Conciso, Convincente, Creíble): filtro de calidad de cualquier copy.
- **ACCA** (Atención → Comprensión → Convicción → Acción): buena alternativa a AIDA en redes.

Regla de oro: combina (ej. PAS en el gancho, FAB en el valor, AIDA al cerrar). No te quedes con uno solo.

Cuándo:
- Tráfico frío / no conocen el producto → prioriza PAS (+ hook de dolor específico).
- Ya conocen la solución → BAB / testimonios / transformación.
- Specs o ficha de producto → FAB antes de pedir la acción.
- Pieza corta redes → ACCA o AIDA compacto; revisa con 4 C's.

## 2) HOOKS (primeros 1–3 segundos)
- En video: gancho visual + auditivo en 1–2 s, antes del texto.
- Específico > vago. Mal: «¿tienes problemas de energía?».
  Bien: «¿sientes que no te alcanzan las horas ni las fuerzas después del trabajo?».
- Tipos: pregunta directa, estadística sorprendente, afirmación audaz, «antes» doloroso de entrada.
- La especificidad debe generar «me está hablando a mí».

## 3) META ADS — 3 NIVELES
1. **Campaña** → objetivo (Leads, Ventas, Tráfico). Decisión crítica; no se cambia tras lanzar.
2. **Conjunto de anuncios** → audiencia, ubicaciones, presupuesto, calendario.
3. **Anuncio** → creativo (imagen/video, texto, título, CTA, URL).

Práctica 2026:
- 3–5 variaciones de creativo por conjunto (hooks, formatos, propuestas distintas).
- Renovar creativo cada 3–4 semanas (fatiga).
- Menos conjuntos, más grandes, más diversidad de creativos (evitar sobre-segmentar).
- CTA alineado al objetivo (no «Comprar» si el objetivo es solo Leads).

## 4) TERMINOLOGÍA VENTA DIRECTA — OBLIGATORIA EN TODO COPY/ASESORÍA
Nunca uses (ni para negar): MLM, multinivel, downline, reclutar, afiliados, pirámide.
Usa siempre: red de franquicias / modelo de venta directa; equipo de crecimiento / construir tu red;
patrocinador / mentor de negocio; socios de negocio / distribuidores independientes.
(Misma regla que módulo Oportunidades — aplica a CUALQUIER contenido de ventas que generes.)

## 5) CONTENIDO CORTO (Reels / TikTok)
- Duración óptima de engagement: **45–60 segundos** (hooks fuertes; valor sostenido).
- Gancho siempre en los primeros **1–3 segundos**.
- Mapea al funnel: frío (dolor/gancho fuerte) vs. caliente (testimonio, transformación, oferta).
""".strip()

_PLAYBOOK_TRIGGERS = re.compile(
    r"(?is)\b(?:"
    r"copy|copies|guion|gui[oó]n|caption|eslogan|slogan|hook|gancho|"
    r"prompt|contenido|campa[nñ]a|anuncio|ads?|meta\s*ads?|facebook\s*ads?|"
    r"instagram\s*ads?|reel|reels|tiktok|funnel|embudo|"
    r"aida|pas\b|pastor|bab\b|fab\b|"
    r"venta|ventas|prospecci[oó]n|cierre|objeci[oó]n|"
    r"estrategia|marketing|publicidad|creativo|lead|leads|"
    r"landing|p[aá]gina\s+de\s+venta|oferta|cta|"
    r"testimonio|transformaci[oó]n|beneficio|"
    r"franquicia|fitline|activiz|restorate|pm\s*international|pm\s*internacional"
    r")\b"
)


def wants_sales_marketing_playbook(text: str) -> bool:
    """True si el turno pide copy, campaña, contenido o asesoría de ventas."""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    return bool(_PLAYBOOK_TRIGGERS.search(t))


def append_sales_marketing_playbook_if_needed(system: str, user_text: str) -> str:
    """Inyecta el playbook cuando el turno es de marketing/ventas/copy."""
    if not wants_sales_marketing_playbook(user_text):
        return system
    base = (system or "").rstrip()
    if not base:
        return CED_SALES_MARKETING_PLAYBOOK
    if "PLAYBOOK INTERNO — MARKETING" in base:
        return base
    return f"{base}\n\n{CED_SALES_MARKETING_PLAYBOOK}"
