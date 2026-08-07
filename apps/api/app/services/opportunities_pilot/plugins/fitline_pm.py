"""Plugin FitLine / PM International — contenido curado + anclas de búsqueda.

Tono UI (excepto Limitaciones/riesgos): red de franquicias, equipo de crecimiento,
socios de negocio, ingresos residuales. Sin "MLM"/"afiliados"/"multinivel" en copy
visible de secciones soft.

Datos duros de empresa: sitio oficial, Direct Selling News / DSA y fuentes
verificables. Precios de entrada y % del Income Plan: Partner Area / materiales
del patrocinador — NO inventar desde web de terceros.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

OPPORTUNITY_ID = "fitline_pm"

_CURATED_AS_OF = "2026-08-07"


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
            "PM International",
            "FitLine",
            "PM International FitLine",
        ],
        "media": {
            "what_is_youtube_id": "2kGPd94Ou4o",
            "what_is_youtube_url": "https://youtu.be/2kGPd94Ou4o",
        },
        "sponsorship": {
            "url": sponsor,
            "cta_label": "Activar su negocio (paquete manager)",
            "configured": bool(sponsor),
        },
        "curated": {
            "as_of": _CURATED_AS_OF,
            "sources": [
                {
                    "title": "PM-International — About (sitio oficial)",
                    "url": "https://www.pm-international.com/gb/en-us/about",
                },
                {
                    "title": "PM-International (sitio corporativo)",
                    "url": "https://www.pm-international.com/",
                },
                {
                    "title": "FitLine Shop EE.UU. (catálogo oficial)",
                    "url": "https://www.fitline.com/us/en-us/products",
                },
                {
                    "title": "FitLine (marca de productos)",
                    "url": "https://www.fitline.com/",
                },
                {
                    "title": "Portal oficial de registro PM (pmebusiness)",
                    "url": "https://www.pmebusiness.com/",
                },
                {
                    "title": "Direct Selling News — Global 100 (ranking venta directa)",
                    "url": "https://www.directsellingnews.com/",
                },
            ],
            "sections": {
                "what_is": {
                    "attribution": "curated",
                    "body": (
                        "PM International (PM-International AG) es la empresa detrás de "
                        "FitLine: nutrición, fitness y belleza con tecnología NTC "
                        "(Nutrient Transport Concept). Quienes activan su negocio pueden "
                        "comercializar productos FitLine y construir un equipo de "
                        "crecimiento (red de franquicias) con posibilidad de ingresos "
                        "residuales, además de la venta de producto a clientes finales.\n\n"
                        "Escala publicada (fuentes corporativas / Direct Selling News, "
                        "as_of 2026): sede en Schengen (Luxemburgo); presencia en más de "
                        "40–45 países; 1.000+ empleados; ranking #6 en el Top 100 Global "
                        "de venta directa; ingresos reportados ~$3.22 mil millones (2025); "
                        "hito de más de mil millones de productos FitLine vendidos "
                        "(anunciado en 2026).\n\n"
                        "CED es la herramienta de estrategia, copy y prospección para "
                        "hacer crecer este negocio — no sustituye el Partner Area ni el "
                        "Income Plan oficial."
                    ),
                },
                "company_history": {
                    "attribution": "curated",
                    "body": (
                        "Historia y presencia (fuentes verificables: sitio oficial "
                        "PM-International / About, Direct Selling News; curado "
                        f"{_CURATED_AS_OF}):\n\n"
                        "• Fundación: 1993 en Speyer, Alemania, por Rolf Sorg "
                        "(co-fundadora Vicki Sorg; hoy también vinculada a labor "
                        "filantrópica de la empresa).\n"
                        "• Marca FitLine: línea principal de nutrición / bienestar "
                        "(primeros productos a mediados de los 90).\n"
                        "• Sede internacional actual: Schengen, Luxemburgo "
                        "(desde 2015). Sedes / operaciones regionales también en "
                        "Europa (Alemania), Asia-Pacífico y Américas.\n"
                        "• Presencia: más de 40–45 países; más de 1.000 empleados "
                        "(cifras corporativas publicadas).\n"
                        "• Escala 2025–2026 (publicada / anunciada): ingresos "
                        "~$3.22 mil millones (2025); ranking #6 Top 100 Direct "
                        "Selling News Global; más de mil millones de productos "
                        "FitLine vendidos a nivel mundial (hito 2026).\n"
                        "• Años en el mercado: desde 1993 (~33 años a 2026).\n\n"
                        "Los números de ventas, ranking y filiales se actualizan: "
                        "verifique siempre About / comunicados oficiales vigentes. "
                        "NO invente cifras no listadas aquí."
                    ),
                },
                "science_credibility": {
                    "attribution": "curated",
                    "body": (
                        "Ciencia, legalidad y respaldo deportivo (fuentes oficiales / "
                        "verificables; curado "
                        f"{_CURATED_AS_OF}):\n\n"
                        "• Tecnología NTC (Nutrient Transport Concept): concepto "
                        "central FitLine — entrega de nutrientes cuándo y dónde el "
                        "cuerpo los necesita, a nivel celular (claim de marca; no "
                        "inventar claims médicos).\n"
                        "• Más de 70 patentes; colaboración citada con la Universidad "
                        "de Trier y ELAB Analytic GmbH para control de calidad.\n"
                        "• Verificación de calidad: cada producto puede verificarse "
                        "escaneando un código QR con resultados de análisis "
                        "independientes (diferenciador que la empresa destaca frente "
                        "a competidores).\n"
                        "• Legalidad del plan de marketing: la corte de apelaciones "
                        "alemana en Frankfurt confirmó la legalidad del plan de PM "
                        "en 2011.\n"
                        "• Venta directa justa: certificación TÜV Hessen desde 2013 "
                        "(verificada anualmente según materiales corporativos).\n"
                        "• Deporte: más de 1.000 atletas de alto rendimiento en 85+ "
                        "disciplinas y 40+ países; proveedor oficial de varias "
                        "federaciones nacionales (p. ej. esquí alemán/austríaco/"
                        "polaco, hockey sobre hielo alemán, ciclismo alemán, "
                        "atletismo alemán — según listados corporativos).\n\n"
                        "Al crear copy o prospección: use estos hechos con tono "
                        "creíble (4 C's). No invente estudios clínicos ni "
                        "certificaciones no listadas."
                    ),
                },
                "products": {
                    "attribution": "curated",
                    "body": (
                        "Productos clave FitLine (función — fuentes: fitline.com / "
                        "materiales de marca; NO invente SKUs ni claims de salud "
                        "no confirmados):\n\n"
                        "• FitLine Optimal Set — producto insignia; nutrición diaria "
                        "integral (combinaciones que suelen incluir PowerCocktail + "
                        "Restorate, o Activize + Basics + Restorate, según mercado).\n"
                        "• FitLine PowerCocktail — vitaminas y minerales orientados "
                        "a energía / aporte diario.\n"
                        "• FitLine Activize (Activize Oxyplus; typo frecuente "
                        "«Activise») — energía natural; muy usado en contenido de "
                        "venta.\n"
                        "• FitLine Restorate — recuperación y balance mineral "
                        "(variantes Citrus / Exotic, etc.).\n"
                        "• FitLine Basics — fibra y probióticos.\n"
                        "• Tecnología transversal: NTC (ver sección Ciencia).\n\n"
                        "Otras líneas del catálogo oficial (existen en tienda; "
                        "descríbalas solo si el usuario pregunta o si aparecen en "
                        "lista de precios de su mercado): Generation 50+, Munogen, "
                        "ProShape, TopShape, microSolve, Women+/Men+, belleza "
                        "(Ultimate Young, etc.).\n\n"
                        "Precios de lista (referencia tienda oficial EE.UU. "
                        "fitline.com/us, snapshot previo — VARÍAN por país, impuestos "
                        "y promo; confirme en la tienda de su mercado):\n"
                        "• Optimal-Set (variantes): ~$146.00\n"
                        "• PowerCocktail: ~$119.48 · Activize Oxyplus: ~$41.20\n"
                        "• Restorate Citrus/Exotic: ~$29.90 · Basics: ~$78.28\n"
                        "• Generation 50+: ~$112.50 · otros SKUs en tienda oficial.\n\n"
                        "CED no inventa productos ni precios fuera de fuentes "
                        "oficiales o del material que el patrocinador comparta."
                    ),
                },
                "how_it_works": {
                    "attribution": "curated",
                    "body": (
                        "El modelo combina:\n"
                        "• Venta de productos FitLine a clientes finales (tienda del "
                        "socio / Customer Direct Program de PM).\n"
                        "• Construcción de un equipo de crecimiento / socios de "
                        "negocio en una red de franquicias.\n"
                        "• Ingresos residuales ligados al volumen de producto y al "
                        "desarrollo del equipo, según el PM Income Plan oficial "
                        "(Partner Area — detalle numérico NO se inventa desde la web).\n\n"
                        "Según reglas oficiales de contrato: la remuneración está "
                        "ligada a la venta de productos FitLine; no se remunera el "
                        "mero acto de invitar personas sin ventas de producto.\n\n"
                        "Terminología obligatoria en todo copy/asesoría: red de "
                        "franquicias / venta directa; equipo de crecimiento; "
                        "patrocinador/mentor; socios de negocio. NUNCA: MLM, "
                        "multinivel, downline, reclutar, afiliados, pirámide.\n\n"
                        "CED acompaña con estrategia y prospección; no sustituye "
                        "información oficial de PM ni garantiza resultados."
                    ),
                },
                "requirements": {
                    "attribution": "curated",
                    "body": (
                        "Planes de inscripción / activación — IMPORTANTE:\n"
                        "Los precios exactos de entrada y la estructura completa "
                        "actualizada del plan de compensación 2026 VARÍAN por "
                        "país/región y viven en el back-office oficial "
                        "(Partner Area) y en el enlace del patrocinador. "
                        "NO están fiables si se inventan desde blogs o terceros.\n\n"
                        "Regla CED:\n"
                        "1) Use primero el enlace de patrocinio de este módulo y "
                        "cualquier material que el patrocinador comparta en CED.\n"
                        "2) Si no hay cifra verificable en este contexto, diga que "
                        "debe confirmarse en el portal / con el mentor — NO invente.\n"
                        "3) Nombres frecuentes de paquetes de entrada (orientativos; "
                        "confirme en su enlace): Starter Kit / Business Set; "
                        "Teampartner Start (autoship); Manager Quickstart; "
                        "variantes Generation 50+; Startup 25.\n\n"
                        "Snapshots históricos de portal (solo referencia — pueden "
                        "estar desactualizados):\n"
                        "• Starter Kit EE.UU. ~$26–30; zona € ~€20 (demo set).\n"
                        "• Teampartner / autoship Optimal-Set: orden de ~$100/mes "
                        "EE.UU. o equivalente € según mercado.\n"
                        "• Manager Quickstart (varios Optimal-Set): orden de "
                        "centenas de USD/EUR según país.\n\n"
                        "Requisitos generales: registro vía patrocinador, "
                        "Distributor Rules / Income Plan del Partner Area, "
                        "políticas locales (edad, residencia, marca).\n\n"
                        "Confirme SIEMPRE en su enlace de activación. CED no inventa "
                        "cifras de inscripción."
                    ),
                },
                "income_potential": {
                    "attribution": "curated",
                    "body": (
                        "Plan de compensación — fuente de verdad: PM Income Plan "
                        "del Partner Area + materiales del patrocinador. "
                        "Detalle de % , umbrales de puntos y requisitos de rango "
                        "NO está completo en fuentes públicas confiables; "
                        "CED NO inventa tablas de comisión ni promesas de ingreso.\n\n"
                        "Cómo se gana (marco oficial, sin cifras inventadas):\n"
                        "• Margen / Retail Income: diferencia precio socio vs. "
                        "cliente.\n"
                        "• Bonificaciones por volumen de clientes referidos "
                        "(Customer Direct) y por actividad del equipo de "
                        "crecimiento, según criterios del plan.\n"
                        "• Ingresos residuales (royalties / overrides) ligados al "
                        "volumen de producto en líneas de socios desarrollados.\n"
                        "• Bonos de liderazgo / management y pools, según rango.\n"
                        "• Incentivos de estilo de vida en rangos altos (p. ej. "
                        "auto, pensión) SOLO si el Income Plan de su país los "
                        "incluye.\n\n"
                        "Avance de niveles (nombres frecuentes; requisitos exactos "
                        "solo en Income Plan): Team Partner → Manager → Sales "
                        "Manager → Marketing Manager → International Marketing "
                        "Manager → Vice President → Executive Vice President → "
                        "President's Team (y superiores según plan local).\n\n"
                        "Pago: liquidación mensual según reglas publicadas "
                        "(umbrales de transferencia aplican).\n\n"
                        "Si el usuario pregunta por % o montos concretos y no hay "
                        "documento del patrocinador en contexto: diga con claridad "
                        "que debe revisarlo en Partner Area / con su mentor — "
                        "ofrezca en cambio estrategia de prospección y venta de "
                        "producto basada en hechos de empresa/productos de esta ficha."
                    ),
                },
                "prospecting": {
                    "attribution": "curated",
                    "body": (
                        "Prospección eficiente en redes (PM/FitLine + expertise "
                        "CED de marketing/ventas):\n\n"
                        "Aplique el playbook interno CED (AIDA/PAS/BAB/FAB, hooks "
                        "específicos, Meta Ads 3 niveles, Reels 45–60 s) SIN "
                        "nombrar frameworks al usuario salvo que pregunte.\n\n"
                        "Ángulos con hechos verificables (no genéricos):\n"
                        "• Dolor concreto + producto (PAS): energía post-trabajo → "
                        "Activize; recuperación → Restorate; rutina diaria → "
                        "Optimal Set / Basics.\n"
                        "• Credibilidad (4 C's): NTC + QR/ELAB, 70+ patentes, "
                        "TÜV Hessen, legalidad 2011, atletas/federaciones, "
                        "escala #6 / $3.22B — sin sonar a exageración.\n"
                        "• BAB: antes (cansancio, inconsistencia) → después "
                        "(rutina FitLine) → puente (probar Optimal Set / "
                        "Activize).\n"
                        "• Embudo: contenido frío (dolor/hook 1–3 s) vs. caliente "
                        "(testimonio, transformación, invitación a conversar / "
                        "enlace de patrocinio).\n"
                        "• Meta Ads: objetivo Leads o Tráfico alineado al CTA; "
                        "3–5 creativos por conjunto; renovar cada 3–4 semanas.\n"
                        "• Terminología: siempre red de franquicias / equipo de "
                        "crecimiento / socios de negocio / patrocinador.\n\n"
                        "Entregables típicos que CED debe producir YA: hooks, "
                        "copy de Reel, captions, prompts, secuencias de DM, "
                        "outline de campaña — usando productos y hechos de esta "
                        "ficha, sin preguntar qué es FitLine ni inventar comisiones."
                    ),
                },
                "getting_started": {
                    "attribution": "curated",
                    "body": (
                        "Pasos sugeridos para activar su negocio:\n"
                        "1. Revisar productos FitLine en la tienda oficial de su "
                        "país y credenciales (NTC, calidad QR, deporte) para su "
                        "narrativa.\n"
                        "2. Confirmar paquete de entrada e Income Plan con el "
                        "enlace de patrocinio / Partner Area (no con blogs).\n"
                        "3. Registrarse vía el CTA de Afiliación de este módulo.\n"
                        "4. Completar mentoría con el equipo del patrocinador.\n"
                        "5. Usar CED para copy, prospección, Viabilidad y "
                        "Tendencias — con terminología correcta.\n"
                        "6. Cumplir políticas de marca, publicidad e Income Plan "
                        "de PM International."
                    ),
                },
                "affiliation": {
                    "attribution": "curated",
                    "body": (
                        "Quienes se registren a través del enlace personal de "
                        "patrocinio de este módulo obtienen acceso a mentoría "
                        "directa y acompañamiento estratégico de un equipo "
                        "especializado (programa de mentoría y desarrollo "
                        "empresarial).\n\n"
                        "Ese mismo canal es la fuente preferida para precios de "
                        "entrada y detalle del plan de compensación vigentes en "
                        "su país — CED prioriza esa información sobre rumores "
                        "de internet.\n\n"
                        "CED es la herramienta de estrategia, copy y prospección "
                        "para hacer crecer el negocio una vez activado.\n\n"
                        "Use el botón «Activar su negocio (paquete manager)» "
                        "para abrir el enlace de registro. Si el enlace aún no "
                        "está configurado en el servidor, aparecerá un aviso en "
                        "esta ficha."
                    ),
                },
                "risks": {
                    "attribution": "curated",
                    "body": (
                        "Limitaciones y riesgos (información explícita del modelo "
                        "real):\n"
                        "• Modelo de venta directa con estructura de comisiones "
                        "por red: los ingresos suelen depender de ventas personales "
                        "y del volumen del equipo de crecimiento.\n"
                        "• El ingreso no está garantizado. Muchas personas obtienen "
                        "resultados bajos o nulos sin ventas consistentes ni "
                        "desarrollo de red.\n"
                        "• Puede haber costo de paquete de inicio / inventario / "
                        "autoship; evalúe presupuesto antes de activar.\n"
                        "• Precios de producto y paquetes cambian por país y fecha; "
                        "no use cifras de esta ficha como cotización vinculante.\n"
                        "• El detalle de porcentajes y requisitos de rango está en "
                        "el Income Plan del Partner Area; CED no inventa tablas "
                        "de comisión ni las «completa» con fuentes no oficiales.\n"
                        "• Regulaciones locales sobre venta directa y publicidad "
                        "de ingresos; no haga afirmaciones engañosas.\n"
                        "• CED no es un patrocinador oficial de PM International "
                        "ni garantiza aceptación, rangos o comisiones."
                    ),
                },
            },
        },
    }
