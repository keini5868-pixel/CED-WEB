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

OPPORTUNITY_ID = "fitline_pm"

_CURATED_AS_OF = "2026-08-12-americas-timeline-verified"


def _sponsorship_url(user_id: str | None = None) -> str:
    from app.services.opportunities_pilot.fitline_sponsor import resolve_sponsor_url

    return str(resolve_sponsor_url(user_id).get("url") or "")


def fitline_pm_plugin(user_id: str | None = None) -> dict[str, Any]:
    from app.services.opportunities_pilot.fitline_sponsor import resolve_sponsor_url

    sponsor_info = resolve_sponsor_url(user_id)
    sponsor = str(sponsor_info.get("url") or "")
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
            "cta_label": sponsor_info.get("cta_label")
            or "Activar su franquicia (paquete manager)",
            "configured": bool(sponsor),
            "source": sponsor_info.get("source") or "none",
            "has_own": bool(sponsor_info.get("has_own")),
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
                {
                    "title": "Direct Selling Association (contexto industria)",
                    "url": "https://www.dsa.org/",
                },
                {
                    "title": "Wikipedia — PM-International (contexto; verificar vs oficial)",
                    "url": "https://en.wikipedia.org/wiki/PM-International",
                },
            ],
            "sections": {
                "what_is": {
                    "attribution": "curated",
                    "body": (
                        "PM International (PM-International AG) es la empresa detrás de "
                        "FitLine: nutrición, fitness y belleza con tecnología NTC "
                        "(Nutrient Transport Concept) — entrega de nutrientes exactamente "
                        "cuándo y dónde el cuerpo los necesita, a nivel celular.\n\n"
                        "Fundada en 1993 en Limburgerhof (Alemania) por Rolf Sorg "
                        "(junto a Vicki Sorg). HQ europeo / logística en Speyer. "
                        "Sede internacional actual: Schengen, Luxemburgo (desde 2015).\n\n"
                        "Escala verificada (Business Wire / Direct Selling News / sitio "
                        f"oficial; curado {_CURATED_AS_OF}): 40–45+ países / 45+ "
                        "subsidiarias; ~1.000+ empleados; ~900+ millones de productos "
                        "FitLine vendidos (claim oficial nov 2025); ventas globales "
                        "~$4 mil millones en 2025 (vs ~$3.25 mil millones en 2024 y "
                        "~$1.71 mil millones en 2020); décadas de crecimiento consecutivo; "
                        "meta pública ~$5 mil millones hacia 2027; ranking #6 venta "
                        "directa (DSN Global 100).\n\n"
                        "Expansión América (momento clave de cierre — ver sección "
                        "americas_expansion): timeline 2019→2025 con HQ Americas de "
                        "50.000 pies² en Sarasota/Manatee (10 nov 2025, $22M fase 1), "
                        "PM Labs, Made in USA desde feb 2025, 100 empleos fase 1 "
                        "(meta ~500). La marca sigue en fase temprana de conocimiento "
                        "entre muchos consumidores estadounidenses pese a la "
                        "trayectoria global.\n\n"
                        "Quienes activan su negocio comercializan FitLine y pueden "
                        "construir un equipo de crecimiento (red de franquicias) con "
                        "ingresos residuales ligados a venta de producto — no al mero "
                        "acto de invitar. Rangos / Income Plan: solo Partner Area.\n\n"
                        "CED es la herramienta de estrategia, copy y prospección. "
                        "NO sustituye Partner Area ni el Income Plan oficial. "
                        "Precios de entrada y % de compensación NO son públicos "
                        "fiables: viven en el back-office del distribuidor / patrocinador."
                    ),
                },
                "company_history": {
                    "attribution": "curated",
                    "body": (
                        "Historia y presencia (fuentes: Business Wire nov 2025, "
                        "Direct Selling News, Wikipedia/registro corporativo, sitio "
                        f"oficial; curado {_CURATED_AS_OF}):\n\n"
                        "• Fundación: 1993 en Limburgerhof, Alemania, por Rolf Sorg "
                        "(junto a Vicki Sorg). Primera sucursal extranjera: Polonia "
                        "(1993).\n"
                        "• Marca FitLine: línea principal de nutrición / bienestar / "
                        "belleza.\n"
                        "• Speyer (Alemania): HQ europeo / centro logístico (ampliado "
                        "desde ~2003; no es el lugar de fundación).\n"
                        "• Sede internacional actual: Schengen, Luxemburgo "
                        "(desde 2015). HQ Asia-Pacífico: Singapur (desde ~2015).\n"
                        "• Presencia: 40–45+ países; 45+ subsidiarias; ~1.000+ empleados.\n"
                        "• Escala: ~900+ millones de productos FitLine vendidos "
                        "(claim oficial); ventas ~$4 mil millones en 2025 "
                        "(~$3.25 mil millones en 2024; ~$1.71 mil millones en 2020); "
                        "meta ~$5 mil millones hacia 2027; ranking #6 global venta "
                        "directa (DSN Global 100).\n"
                        "• Años en el mercado: desde 1993 (~33 años a 2026), con "
                        "crecimiento consecutivo reportado por la empresa / DSN.\n\n"
                        "EXPANSIÓN AMÉRICA (Sarasota / Manatee, Florida) — ver sección "
                        "americas_expansion (timeline 2019–2025 verificada).\n\n"
                        "NO invente filiales, cifras ni hitos no listados aquí. "
                        "Si piden un dato de ranking/ingresos muy reciente fuera de "
                        "este bloque y lo piden explícitamente de internet, ahí sí "
                        "puede usarse búsqueda web como respaldo."
                    ),
                },
                "americas_expansion": {
                    "attribution": "curated",
                    "body": (
                        "Expansión América / EE.UU. — línea de tiempo VERIFICADA "
                        "(Business Wire 10–11 nov 2025 / Direct Selling News; "
                        f"curado {_CURATED_AS_OF}). Usar en cierre cuando pregunten "
                        "cómo unirse / timing / EE.UU. / franquicia:\n\n"
                        "LÍNEA DE TIEMPO\n"
                        "• 2019 — primeras operaciones en América (oficinas rentadas); "
                        "inicio de la Sede Americas en el área Sarasota, Florida.\n"
                        "• 2021 — primer almacén propio (~10.000 pies² / ~930 m²).\n"
                        "• 2022 — segundo almacén.\n"
                        "• 2023 — centro de servicio (~3.500 pies² / ~325 m²) para "
                        "distribuidores en las Américas.\n"
                        "• Feb 2025 — inicio de producción / blending in-house "
                        "«Made in USA» y PM Labs (primer laboratorio propio de "
                        "calidad en América) como parte del plan de infraestructura.\n"
                        "• 10 nov 2025 — inauguración (ribbon-cutting) del nuevo "
                        "Americas HQ: 50.000 pies² en Sarasota / Manatee County, "
                        "Florida; inversión ~$22 millones (fase 1 de 4); hub "
                        "estratégico, manufactura y logística para Norte, Centro y "
                        "Sudamérica; >21.800 pies² de logística; potencial de "
                        "escalar hasta ~$500 millones en ventas retail anuales en "
                        "esta primera fase (claim de la empresa).\n"
                        "• Empleos: ~100 en fase 1; meta de hasta ~500 a mediano "
                        "plazo (operaciones, manufactura, logística).\n"
                        "• Capacidad futura: terreno adquirido alrededor del HQ; "
                        "expansión potencial hasta ~188.000 pies² en fases "
                        "adicionales (inversión total proyectada ~$50M en fases "
                        "posteriores según reportes de industria).\n"
                        "• Mercado potencial citado por la empresa: ~$11.69 mil "
                        "millones en ~5.55 millones de clientes principales "
                        "(nicho premium — claim de la empresa, no proyección CED).\n"
                        "• Kick-Off USA 2026: evento oficial de lanzamiento USA en "
                        "Sarasota (fecha confirmada en canales PM USA: 24 ene 2026). "
                        "NO invente otras fechas de Kick-Off.\n\n"
                        "ÁNGULO DE CIERRE (tono profesional de red de franquicias — "
                        "NO telemarketing):\n"
                        "Cuando el usuario pida unirse al negocio / «cómo empiezo» / "
                        "franquicia / ser socio o manager: presentar la oportunidad "
                        "de posicionarse como nuevo socio/manager en un momento de "
                        "expansión activa en América, construyendo su equipo de "
                        "crecimiento (red de franquicias) mientras el mercado "
                        "americano sigue abriéndose — con respaldo global (~$4B "
                        "ventas 2025, décadas de trayectoria) y fase temprana de "
                        "conocimiento de marca en EE.UU. Usar terminología: rangos, "
                        "red de franquicias, equipo de crecimiento, socio/manager, "
                        "ingresos residuales ligados a producto. "
                        "PROHIBIDO inventar % del Income Plan o precios de entrada → "
                        "Partner Area / enlace OPPS / patrocinador.\n\n"
                        "En asesoría: preguntar si está listo para iniciar su "
                        "franquicia; si alguien le compartió la oportunidad, "
                        "sugerir contactar a esa persona; guiar a Oportunidades "
                        "(OPPS) para inscripción."
                    ),
                },
                "science_credibility": {
                    "attribution": "curated",
                    "body": (
                        "Ciencia, calidad, anti-dopaje, legalidad y deporte "
                        "(fuentes oficiales / Business Wire / ATP / Cologne List; "
                        f"curado {_CURATED_AS_OF}):\n\n"
                        "TECNOLOGÍA Y CALIDAD\n"
                        "• NTC® (Nutrient Transport Concept): claim de marca — "
                        "nutrientes cuándo y dónde se necesitan, a nivel celular. "
                        "NO inventar claims médicos ni estudios clínicos no listados.\n"
                        "• Más de 70 patentes (claim de la empresa); colaboración "
                        "con laboratorios independientes (ELAB Analytics GmbH).\n"
                        "• QR en empaque con resultados de análisis independientes "
                        "(transparencia promovida por la empresa).\n"
                        "• Manufactura bajo estándares GMP; en Americas HQ: "
                        "producción GMP-certified y camino a certificaciones "
                        "adicionales (p. ej. NSF) según anuncio oficial nov 2025.\n"
                        "• Históricamente «Made in Germany»; desde feb 2025 también "
                        "blending / producción in-house en EE.UU. (Made in USA) "
                        "según anuncio de infraestructura.\n\n"
                        "CERTIFICACIÓN ANTI-DOPAJE — Cologne List®\n"
                        "• Productos de suplementación FitLine publicados en la "
                        "Cologne List® desde hace ~20 años (koelnerliste.com; "
                        "confirmado en comunicados ATP/FitLine).\n"
                        "• Rol fundador / apoyo temprano: citar como claim de la "
                        "empresa.\n"
                        "• «Cero casos positivos»: solo como comunicación de la "
                        "empresa, no como garantía absoluta de CED.\n\n"
                        "LEGALIDAD Y VENTA JUSTA\n"
                        "• Referencias históricas de industria: legalidad en "
                        "Alemania (Frankfurt ~2011) y certificación de venta justa "
                        "TÜV Hessen desde ~2013 (verificación anual) — no inventar "
                        "fallos ni victorias judiciales nuevas.\n\n"
                        "ALIANZAS DEPORTIVAS (Business Wire nov 2025 + ATP jul 2024)\n"
                        "• FitLine: Official Sports Nutrition Partner y Official "
                        "Energy Bar Partner del ATP Tour (acuerdo multi-año hacia "
                        "2026).\n"
                        "• Federaciones citadas por PM: DEB (hockey hielo DE), ÖSV "
                        "(esquí AT), BDR (ciclismo DE), FIP (baloncesto IT), KWF "
                        "(lucha Corea), y otras según material oficial.\n"
                        "• Claim oficial: 1.000+ atletas / 85+ disciplinas / 40+ "
                        "países.\n"
                        "• NO invente NFL/NBA como partners actuales: nov 2025 habla "
                        "de apuntar a NSF para colaborar con atletas/ligas élite en "
                        "EE.UU. — es objetivo, no partnership firmado.\n\n"
                        "En copy/prospección use estos hechos con tono creíble. "
                        "No invente certificaciones ni respaldo no listado."
                    ),
                },
                "social_responsibility": {
                    "attribution": "curated",
                    "body": (
                        "Responsabilidad social — Fundación «PM We Care» "
                        f"(curado {_CURATED_AS_OF}; cifras = claims de la empresa):\n\n"
                        "• Más de $3 millones donados (claim de marca).\n"
                        "• Más de 800 apadrinamientos de niños (claim de marca).\n\n"
                        "Use este ángulo en copy de marca/credibilidad cuando "
                        "aporte al mensaje; no invente montos ni programas "
                        "adicionales no listados aquí."
                    ),
                },
                "products": {
                    "attribution": "curated",
                    "body": (
                        "CATÁLOGO FITLINE AMPLIADO (nombres oficiales por categoría — "
                        f"curado {_CURATED_AS_OF}). Tecnología transversal: NTC. "
                        "NO invente SKUs, claims médicos ni descripciones clínicas "
                        "fuera de esta lista. Disponibilidad y nombres exactos pueden "
                        "variar por país/Partner Area.\n\n"
                        "NUTRICIÓN BASE\n"
                        "• Optimal-Set (Optimal Set) — producto insignia; nutrición "
                        "diaria integral (combos frecuentes: PowerCocktail+Restorate; "
                        "Activize+Basics+Restorate; variantes Citrus/Exotic).\n"
                        "• PowerCocktail — vitaminas y minerales para energía/"
                        "vitalidad.\n"
                        "• PowerCocktail Junior — línea junior (niños/jóvenes; "
                        "confirme edad/mercado en su tienda).\n"
                        "• Restorate — recuperación y balance mineral "
                        "(variantes Citrus / Exotic).\n"
                        "• Generation 50+ — nutrición orientada a 50+.\n"
                        "• Activize Oxyplus (typo frecuente «Activise») — energía "
                        "natural; muy usado en copy de venta.\n"
                        "• Basics — fibra y probióticos.\n\n"
                        "DEPORTE / FITNESS\n"
                        "• Endurance\n"
                        "• Protein Max\n"
                        "• Protein\n"
                        "• ProShape (Amino)\n"
                        "• Whey\n"
                        "• Fitness-Drink\n"
                        "• PowerMeal Bar\n"
                        "• Joint-Health Set\n\n"
                        "CONTROL DE PESO\n"
                        "• Get in Shape\n"
                        "• ProShape All-in-1\n"
                        "• ProShape 2 Go (ProShape 2Go)\n"
                        "• Nota: hay más SKUs de control de peso en algunos mercados — "
                        "si el usuario aporta ficha de Partner Area / tienda local, "
                        "úselo; no invente nombres.\n\n"
                        "ESPECIALES / MICROSOLVE Y OTROS\n"
                        "• Zellschutz (Antioxy)\n"
                        "• IB5 (IB⁵)\n"
                        "• Munogen\n"
                        "• Basen Plus\n"
                        "• D-Drink\n"
                        "• Herbaslim Tea\n"
                        "• Fruit Bar\n"
                        "• Activize Power Drink\n"
                        "• Feel Good Yoghurt\n"
                        "• microSolve HeartDuo\n"
                        "• microSolve Omega 3\n"
                        "• microSolve Q10 Plus\n"
                        "• microSolve Lutein\n"
                        "• microSolve Isoflavona (Isoflavone)\n\n"
                        "BELLEZA Y OTRAS LÍNEAS\n"
                        "• Categoría Belleza y más control de peso: el desglose "
                        "completo no está curado aquí. Si aparece en material del "
                        "patrocinador o tienda oficial del país (p. ej. Ultimate Young, "
                        "Hydrating Shot, Women+/Men+, TopShape), úselo; si no, diga "
                        "que confirme en Partner Area / fitline.com local — "
                        "NO invente la línea.\n\n"
                        "PRECIOS DE LISTA (solo referencia tienda EE.UU. fitline.com — "
                        "snapshot; VARÍAN por país/promo; NO son precios de entrada "
                        "al negocio):\n"
                        "• Optimal-Set (variantes): ~$146.00\n"
                        "• PowerCocktail: ~$119.48 · Activize Oxyplus: ~$41.20\n"
                        "• Restorate Citrus/Exotic: ~$29.90 · Basics: ~$78.28\n"
                        "• Generation 50+: ~$112.50 · otros SKUs: tienda oficial.\n\n"
                        "IMPORTANTE — NO inventar ni buscar en web para «completar»:\n"
                        "• Precios exactos de entrada al negocio\n"
                        "• Estructura/% del Income Plan / plan de compensación "
                        "actualizado (Partner Area / material del patrocinador)\n"
                        "Si el usuario aporta datos verificados de su back-office, "
                        "úselos prioritariamente."
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
                        "patrocinador/mentor; socios de negocio. Evite jerga "
                        "peyorativa del sector; use siempre el lenguaje de "
                        "franquicia y equipo de crecimiento.\n\n"
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
                        "estar desactualizados; confirme en su enlace):\n"
                        "• Starter Kit EE.UU. ~$26.80; zona € ~€19,85 (demo set).\n"
                        "• Teampartner Start / autoship Optimal-Set EE.UU. "
                        "~$105.12/mes (orden de ~$100/mes) o equivalente €.\n"
                        "• Manager Quickstart EE.UU. ~$596.00 (varios Optimal-Set); "
                        "zona € orden de centenas según país.\n"
                        "• Variantes Generation 50+ / Startup 25: confirmar en portal.\n\n"
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
                        "• Credibilidad (4 C's): NTC + QR/ELAB, 70+ patentes, GMP "
                        "Alemania, Cologne List® (anti-dopaje, socio fundador), "
                        "TÜV Hessen, legalidad 2011, ATP/federaciones/atletas, "
                        "PM We Care, escala #6 / $3.22B — sin sonar a exageración.\n"
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
                        "5. Usar CED para copy, prospección, Análisis de Producto y "
                        "Análisis de Tendencia — con terminología correcta.\n"
                        "6. Cumplir políticas de marca, publicidad e Income Plan "
                        "de PM International.\n"
                        "7. Si es nuevo y se traba en el registro o la tienda: "
                        "usar la sección «Entrar a la tienda / Partner Area» "
                        "(checklist de detalles que la gente suele saltarse)."
                    ),
                },
                "store_entry": {
                    "attribution": "curated",
                    "body": (
                        "CHECKLIST DE ENTRADA A LA TIENDA / PARTNER AREA "
                        "(flujo oficial de registro PM; CED no inventa precios ni %):\n"
                        "1) Enlace del patrocinador o Sponsor ID — confirme que el "
                        "nombre en pantalla es quien le presentó; si no, no continúe.\n"
                        "2) País/región correcto (precios y envío cambian).\n"
                        "3) Confirme el correo (sin el mail de confirmación no entra después).\n"
                        "4) Acepte reglas Team Partner; el acuerdo vale cuando PM acepta.\n"
                        "5) Primer pedido: si dice que lo olvidó, puede registrar ya y "
                        "elegir productos luego. Pedido pendiente: «Pagar» retoma; "
                        "«Reiniciar» cancela — no mezcle esos botones.\n"
                        "6) No es obligatorio comprar para ser distribuidor (reglas oficiales).\n"
                        "7) Login Partner Area (partner.pm-international.com). "
                        "PROHIBIDO pegar URL en chat/voz. Si el login falla al inicio, "
                        "el registro puede no estar procesado aún.\n"
                        "8) Use solo la tienda oficial PM (FitLine Shop / PM Office).\n"
                        "9) Guarde número de cliente y correo de confirmación.\n"
                        "Si pregunta «cómo entro a la tienda», «Partner Area», "
                        "«primer pedido» o «me trabé en el registro»: entregue este "
                        "checklist paso a paso."
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
                        "esta ficha. NUNCA copies el URL en un resumen de "
                        "conversación: abre OPPS y guía a bajar hasta el botón."
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
