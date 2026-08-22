"""Catálogo factual de capacidades de producto CED (chat / modo avanzado / voz).

Fuente de verdad para cuando el usuario pide «qué puedes hacer» o una lista
numerada de habilidades. NO inventar módulos (p. ej. WhatsApp) que no existan.
"""

from __future__ import annotations

import re

_CAPABILITY_CATALOG = re.compile(
    r"\b("
    r"habilidades|herramientas|capacidades|funciones|"
    r"qu[eé]\s+(?:puedes|puede|sabe(?:s)?)\s+(?:hacer|hacer\s+ced)|"
    r"todas\s+las\s+(?:habilidades|herramientas|capacidades)|"
    r"lista\s+(?:donde|de)\s+(?:especifique|especificar|capacidades|habilidades|herramientas)|"
    r"sistema\s+ced"
    r")\b",
    re.I,
)
_ENUM_OR_LIST_HINT = re.compile(
    r"\b("
    r"lista|enumera|enumeraci[oó]n|n[uú]mero\s+(?:uno|dos|tres|\d+)|"
    r"por\s+ejemplo\s+n[uú]mero|as[ií]\s+sucesivamente|"
    r"y\s+as[ií]\s+sucesivamente|una\s+por\s+una"
    r")\b",
    re.I,
)

# Lista numerada — solo capacidades reales del producto.
CED_CAPABILITY_CATALOG_BODY = """1. Chat de texto conversacional — consejo, estrategia, creativos y acompañamiento
2. Modo avanzado — análisis profundo de negocio, marketing e investigación
3. Asistente de voz Jarvis — manos libres con las herramientas clave
4. Publicación en Facebook e Instagram (Meta, con confirmación previa del texto)
5. Prospección — detección de leads en comentarios de redes
6. Lectura de comentarios en Facebook/Instagram
7. Generación de imágenes con IA (incluye creativos y texto legible en la imagen cuando lo pida)
8. Variaciones de imagen con referencia — mismo estilo, editar o variar a partir de una foto
9. Generación y descarga de PDF
10. Video — generación con Veo 3 y edición de videos del usuario (módulo VIDEO; piloto / en desarrollo activo con Keini)
11. Búsqueda web en tiempo real — noticias, precios, datos actuales
12. Finanzas personales — consultar resumen y registrar movimientos (con confirmación)
13. Cámara y visión — describir o buscar lo visible (principalmente en voz / panel HUD)
14. Mapa y navegación / modo conducir (principalmente en voz / panel HUD)
15. YouTube — buscar, reproducir, pausar o cerrar en el panel (principalmente en voz)
16. Clima y ambiente — temperatura, pronóstico, calidad del aire y polen
17. Memoria cognitiva — guardar y recuperar preferencias, leads y contexto de sesión
18. Recordatorios en el panel HUD («recuérdame…» / pendientes)
19. Análisis de Producto (producto o servicio, solo si lo pide explícitamente)
20. Análisis de Tendencia de industria (cuando el módulo esté activo)
21. Guiones, copy y calendarios de contenido — entregables listos para usar
22. Mentor de ventas y Meta — cierre, objeciones, funnels y creativos (consejo; no es Ads Manager)
23. WhatsApp Business — conectar un número de negocio y flujos de auto-respuesta por palabra clave (dashboard → Sistema → WhatsApp)
24. Modo Creador — administración del sistema (solo cuando aplica / rol autorizado)

Notas honestas:
- Cámara, mapa/navegación y YouTube viven sobre todo en el asistente de voz y el HUD.
- Publicar en redes requiere Meta conectado en el dashboard.
- Video (Veo 3 + edición): piloto en desarrollo. Abrir módulo VIDEO en el dashboard (?videoEditModule=pilot). Usa tokens de video (no el saldo de voz). Shotstack + Text→SFX; Veo 3 Lite solo cuando el flag de producto lo permita. No prometas render Veo completo si el piloto aún no lo dispara.
- WhatsApp es Cloud API (número de negocio en el dashboard), no el chat personal ni Telegram. No se dispara por voz.
- No integra Google Calendar/email; sí calendarios de contenido y recordatorios HUD."""

# Resumen oral corto — voz / piloto Retell (máx. 5 puntos por turno; ofrecer ampliar).
CED_CAPABILITY_ORAL_SUMMARY = """
Si preguntan qué puedes hacer / habilidades / herramientas del sistema:
enumera en español capacidades REALES (máx. 4-5 puntos por turno; ofrece ampliar). Menciona a Keini Castillo.
Incluye, en turnos sucesivos si hace falta: chat y consejo; modo avanzado; voz Jarvis;
Meta (publicar FB/IG con confirmación, comentarios, prospección); imágenes + variaciones + PDF;
video (Veo 3 + edición de videos del usuario — piloto VIDEO en desarrollo con Keini);
búsqueda web; finanzas; cámara/visión; mapa/navegación; YouTube; clima/ambiente; memoria;
recordatorios HUD; Análisis de Producto; Análisis de Tendencia; guiones/copy; mentor de ventas.
WhatsApp Business: solo el módulo del dashboard (número Cloud API + flujos); no lo operes por voz.
Cuando mencionen video/Veo/editar MP4: di con orgullo que Keini y CED están construyendo esa línea —
módulo VIDEO en el dashboard (piloto), tokens de video, edición con cortes/SFX; Veo 3 en el pipeline
cuando el producto lo habilite. NO inventes que ya renderizas Veo desde la voz sin el módulo.
PROHIBIDO inventar mensajería de terceros (Telegram, SMS, WhatsApp personal), Ads Manager, email o Google Calendar.
Tras generar imagen: NO ofrezcas publicar salvo que lo pidan.
""".strip()

CED_CAPABILITY_CATALOG_REPLY = f"""Aquí tiene las habilidades y herramientas reales del sistema CED, señor:

{CED_CAPABILITY_CATALOG_BODY}

Si quiere, detallo alguna en concreto. Si prefiere exportar esta lista, diga si desea un PDF resumen breve o completo."""

CED_CAPABILITY_CATALOG_SYSTEM_RULE = f"""
LISTA DE CAPACIDADES DE CED (OBLIGATORIO):
Si el usuario pide una lista de habilidades, herramientas, capacidades o «qué puede hacer CED»:
- Responde SOLO con capacidades REALES del producto (usa esta lista o un subconjunto fiel).
- PROHIBIDO inventar módulos que no existan (p. ej. mensajería de terceros, Ads Manager, soporte multiusuario genérico inventado, etc.).
- NO dispares publicación en redes, PDF ni imagen solo porque el usuario las mencione como ejemplo en la lista.
- Si detalla un canal: sé honesto (cámara/mapa/YouTube = principalmente voz/HUD).

Capacidades reales:
{CED_CAPABILITY_CATALOG_BODY}
""".strip()


def is_capability_catalog_request(text: str) -> bool:
    """True si pide enumerar qué sabe hacer CED (no ejecutar una tool concreta)."""
    t = (text or "").strip()
    if len(t) < 24:
        return False
    catalog = bool(_CAPABILITY_CATALOG.search(t))
    enum_hint = bool(_ENUM_OR_LIST_HINT.search(t))
    if catalog and enum_hint:
        return True
    # «qué puedes hacer / habilidades del sistema» sin enumeración explícita
    if re.search(
        r"\b(qu[eé]\s+(?:puedes|puede|sabe(?:s)?)\s+hacer|"
        r"cu[aá]les\s+son\s+(?:tus|sus)\s+(?:habilidades|herramientas|capacidades)|"
        r"todas\s+las\s+(?:habilidades|herramientas)\b)",
        t,
        re.I,
    ):
        return True
    return False


def try_capability_catalog_reply(text: str) -> str | None:
    if not is_capability_catalog_request(text):
        return None
    return CED_CAPABILITY_CATALOG_REPLY
