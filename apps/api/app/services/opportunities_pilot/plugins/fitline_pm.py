"""Plugin FitLine / PM International — contenido curado + anclas de búsqueda.

Tono UI (excepto Limitaciones/riesgos): red de franquicias, equipo de crecimiento,
socios de negocio, ingresos residuales. Sin "MLM"/"afiliados"/"multinivel" en copy
visible de secciones soft.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

OPPORTUNITY_ID = "fitline_pm"

# Soft-tone curated body (all sections except risks). Risks are honest.
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
                    "title": "FitLine Shop EE.UU. (catálogo oficial)",
                    "url": "https://www.fitline.com/us/en-us/products",
                },
                {
                    "title": "Portal oficial de registro PM (pmebusiness)",
                    "url": "https://www.pmebusiness.com/",
                },
                {
                    "title": "FitLine (marca de productos)",
                    "url": "https://www.fitline.com/",
                },
                {
                    "title": "PM-International (sitio corporativo)",
                    "url": "https://www.pm-international.com/",
                },
            ],
            "sections": {
                "what_is": {
                    "attribution": "curated",
                    "body": (
                        "PM-International AG es la empresa detrás de FitLine, una línea de "
                        "nutrición, fitness y belleza. Quienes activan su negocio pueden "
                        "comercializar productos FitLine y construir un equipo de "
                        "crecimiento (red de franquicias) con posibilidad de ingresos "
                        "residuales, además de la venta de producto a clientes finales.\n\n"
                        "Es un negocio familiar económicamente independiente; según su "
                        "página oficial About, figura entre las Top 100 empresas de "
                        "distribución a nivel mundial (puesto 6º citado en esa ficha).\n\n"
                        "CED es la herramienta de estrategia y desarrollo de habilidades "
                        "para hacer crecer este negocio (análisis de viabilidad, "
                        "tendencias y apoyo operativo)."
                    ),
                },
                "company_history": {
                    "attribution": "curated",
                    "body": (
                        "Historia y presencia (fuentes: sitio oficial About de "
                        "PM-International, consultado 2026-08-07):\n\n"
                        "• Fundación: 1993, como PM Cosmetics GmbH; fundador y CEO: "
                        "Rolf Sorg.\n"
                        "• 1995: primer suplemento FitLine (Q10).\n"
                        "• Años posteriores: expansión a Asia, centros logísticos "
                        "(p. ej. Suiza / Speyer, Alemania), apertura de headquarters "
                        "en Luxemburgo y Asia-Pacífico.\n"
                        "• Sede internacional: Luxemburgo; sedes regionales en Europa "
                        "(Alemania), Asia-Pacífico (Singapur) y Américas (Florida, EE.UU.).\n"
                        "• Presencia: más de 40 países, con más de 45 filiales / socios "
                        "de distribución (cifras publicadas en About).\n"
                        "• Hitos citados por la empresa: reconocimiento Top 100 "
                        "innovación (Alemania), 1.000 millones USD en ventas anuales "
                        "(2019 en la línea de tiempo oficial), partner de nutrición "
                        "deportiva de ATP Tour (2024 en esa línea de tiempo).\n\n"
                        "Años en el mercado: desde 1993 (~33 años a 2026).\n\n"
                        "Los números de ventas, ranking y filiales pueden actualizarse: "
                        "verifique siempre la página About vigente."
                    ),
                },
                "products": {
                    "attribution": "curated",
                    "body": (
                        "Catálogo FitLine (precios de lista tienda oficial EE.UU. "
                        "fitline.com/us, consultada 2026-08-07). Los precios varían "
                        "por país, impuestos y promociones; confirme en la tienda de "
                        "su mercado.\n\n"
                        "Optimal supply\n"
                        "• Optimal-Set (PowerCocktail + Restorate Citrus/Exotic): "
                        "$146.00\n"
                        "• Optimal-Set (Activize + Basics + Restorate Citrus/Exotic): "
                        "$146.00\n"
                        "• PowerCocktail: $119.48\n"
                        "• Activize Oxyplus: $41.20\n"
                        "• Activize Peach Ice-Tea: $41.20 (edición limitada)\n"
                        "• Restorate Citrus / Exotic: $29.90 c/u\n"
                        "• Basics: $78.28\n"
                        "• Generation 50+: $112.50\n"
                        "• PowerCocktail Junior: $43.30\n"
                        "• Set Restorate + Activize Oxyplus: $67.00\n"
                        "• Optimal-Set 50+ (PowerCocktail + Restorate + Generation 50+): "
                        "$256.00\n"
                        "• TopShape Starterset (TopShape + PowerCocktail + Restorate): "
                        "$252.04\n"
                        "• TopShape Optimal-Set (+ TopShape + 2× ProShape): $330.20\n\n"
                        "Fitness\n"
                        "• Munogen: $72.60\n"
                        "• ProShape Amino: $70.50\n"
                        "• Whey: $64.90\n"
                        "• Fitness-Drink: $55.10\n\n"
                        "Specialty\n"
                        "• Women+: $65.50 · Men+: $74.35\n"
                        "• microSolve⁺ Heart Duo: $83.25 · Omega 3: $43.50 · "
                        "Lutein: $42.25 · Q10 Plus: $53.60\n"
                        "• Antioxy: $53.60 · Joint-Health: $79.85 · D-Drink: $42.25\n"
                        "• C-Balance: $46.90 · IB⁵: $34.10 · Herbaslim Tea: $16.48\n\n"
                        "Weight management\n"
                        "• TopShape: $108.60\n"
                        "• ProShape All-in-1 Chocolate / Bourbon Vanilla: $47.99 c/u\n"
                        "• Herbaslim Tea: $16.48\n\n"
                        "Beauty (selección)\n"
                        "• Beauty: $61.20 · Activize Serum: $56.65 · 4ever: $73.65\n"
                        "• Ultimate Young: $97.85 · Ultimate Young 4ever: $162.75\n"
                        "• Tonic / Cleansing Lotion: $31.45 c/u · Eye Cream: $56.55\n"
                        "• Cell Lotion: $35.55 · Dental+: $6.68\n"
                        "• Men Face Cream: $33.90 · Q10 Oxy Repair Hands: $13.90\n"
                        "• Young Care (foam/cream/peeling/set): desde $19.90\n"
                        "• Hydrating-Shot Mask: $60.30 · med microSolve Hair+: $46.35\n"
                        "• Triple Lift Set: $145.00 (limitado)\n\n"
                        "Hay FanShop y promociones adicionales en la tienda oficial. "
                        "CED no inventa SKUs ni precios fuera de fuentes oficiales."
                    ),
                },
                "how_it_works": {
                    "attribution": "curated",
                    "body": (
                        "El modelo combina:\n"
                        "• Venta de productos FitLine a clientes finales (tienda propia "
                        "del socio / Customer Direct Program de PM).\n"
                        "• Construcción de un equipo de crecimiento / socios de negocio "
                        "en una red de franquicias.\n"
                        "• Ingresos residuales ligados al volumen de producto y al "
                        "desarrollo del equipo, según el PM Income Plan oficial "
                        "(documentos del Partner Area).\n\n"
                        "Según las reglas oficiales de contrato: la remuneración está "
                        "ligada a la venta de productos FitLine; no se remunera el "
                        "mero acto de invitar personas sin ventas de producto.\n\n"
                        "CED acompaña con estrategia: no sustituye la información oficial "
                        "de PM International ni garantiza resultados."
                    ),
                },
                "requirements": {
                    "attribution": "curated",
                    "body": (
                        "Planes de inscripción / activación (portal oficial de registro "
                        "pmebusiness.com; precios de ejemplo EE.UU. y zona € — "
                        "consultados 2026-08; varían por país):\n\n"
                        "1) Starter Kit (kit de negocio)\n"
                        "   • EE.UU.: ~$26.80 (bolsa demo, botella, 2 vasos, cuchara).\n"
                        "   • Zona € (ej. NL): ~€19,85 (Business Set + botella, vasos, "
                        "cuchara).\n\n"
                        "2) Teampartner Start (entrada con autoship)\n"
                        "   • EE.UU.: ~$105.12/mes — 1 Optimal-Set "
                        "(PowerCocktail+Restorate o Activize+Basics+Restorate); "
                        "descuento autoship ~10%; a menudo bonus Activize Oxyplus.\n"
                        "   • Zona €: ~€86,96/mes — 3× Optimal-Set en ciclo "
                        "(variantes PowerCocktail/Activize+Basics + Restorate).\n\n"
                        "3) Manager Quickstart (arranque acelerado — paquete manager)\n"
                        "   • EE.UU.: ~$596.00 — 6× Optimal-Set + autoship al mes "
                        "siguiente; bonuses frecuentes (p. ej. Activize Serum + Oxyplus).\n"
                        "   • Zona €: ~€478,00 — 6× Optimal-Set (mismas variantes).\n\n"
                        "4) Variantes Generation 50+\n"
                        "   • EE.UU. autoship Optimal-Set 50+: ~$195.12/mes.\n"
                        "   • EE.UU. Manager 50+ (6×): ~$1,075.00.\n"
                        "   • Zona € Manager 50+ (6×): ~€875,00.\n\n"
                        "5) Startup 25 (perfil joven / entrada con Activize)\n"
                        "   • EE.UU.: ~$61.80 (Activize Set con descuento publicado).\n"
                        "   • Zona €: ~€51,20.\n\n"
                        "También suelen ofrecerse add-ons one-time al registrarse "
                        "(p. ej. Activize Serum en promoción).\n\n"
                        "Requisitos generales: registro vía patrocinador, aceptación de "
                        "Distributor Rules / Income Plan del Partner Area, y políticas "
                        "locales (edad, residencia, uso de marca).\n\n"
                        "Confirme precios y disponibilidad en su enlace de activación. "
                        "CED no inventa cifras de inscripción."
                    ),
                },
                "income_potential": {
                    "attribution": "curated",
                    "body": (
                        "Plan de compensación (marco oficial; detalle numérico en el "
                        "PM Income Plan del Partner Area — no inventamos % ni umbrales "
                        "sin documento vigente públicamente verificable):\n\n"
                        "Cómo se gana (según reglas / Income Plan oficiales):\n"
                        "• Margen / Retail Income: diferencia entre precio de socio "
                        "y precio de venta al cliente.\n"
                        "• Bonificaciones por volumen de clientes referidos "
                        "(Customer Direct) y por actividad del equipo de crecimiento, "
                        "cuando se cumplen criterios del plan.\n"
                        "• Ingresos residuales (royalties / overrides) ligados al "
                        "volumen de producto en líneas de socios desarrollados — "
                        "el plan vigente describe generaciones y condiciones.\n"
                        "• Bonos de liderazgo / management y pools, según rango "
                        "alcanzado.\n"
                        "• Incentivos de estilo de vida en rangos altos (p. ej. "
                        "programa de auto, plan de pensión), si el Income Plan de "
                        "su país los incluye.\n\n"
                        "Avance de niveles (nombres frecuentes en materiales PM; "
                        "requisitos exactos de puntos/volumen solo en Income Plan):\n"
                        "Team Partner → Manager → Sales Manager → Marketing Manager → "
                        "International Marketing Manager → Vice President → "
                        "Executive Vice President → President's Team (y rangos "
                        "superiores según plan local).\n\n"
                        "Pago: liquidación mensual; las reglas publicadas indican "
                        "pago a más tardar el día 20 del mes siguiente (con umbral "
                        "mínimo de transferencia).\n\n"
                        "El potencial depende de ventas reales y desarrollo de equipo. "
                        "CED no publica montos de comisión ni promesas de ingreso "
                        "sin fuente verificable de esta sesión."
                    ),
                },
                "getting_started": {
                    "attribution": "curated",
                    "body": (
                        "Pasos sugeridos para activar su negocio:\n"
                        "1. Revisar productos FitLine en la tienda oficial de su país "
                        "y el modelo de ingresos residuales en materiales oficiales.\n"
                        "2. Elegir paquete de entrada (Starter / Teampartner / Manager "
                        "Quickstart / 50+ / Startup 25) según presupuesto y ritmo.\n"
                        "3. Usar el enlace de patrocinio (sección Afiliación) para "
                        "registrarse — el CTA prioriza el paquete manager.\n"
                        "4. Completar mentoría y desarrollo empresarial con el equipo "
                        "asociado a ese enlace.\n"
                        "5. Usar CED (Viabilidad, Tendencias, Oportunidades) como "
                        "herramienta de estrategia y habilidades para crecer.\n"
                        "6. Cumplir políticas de marca, publicidad e Income Plan de "
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
                        "• Puede haber costo de paquete de inicio / inventario / "
                        "autoship; evalúe si encaja con su presupuesto antes de "
                        "activar el negocio.\n"
                        "• Precios de producto y paquetes cambian por país y fecha; "
                        "no use cifras de esta ficha como cotización vinculante.\n"
                        "• El detalle de porcentajes y requisitos de rango está en el "
                        "Income Plan del Partner Area; CED no inventa tablas de "
                        "comisión.\n"
                        "• Está sujeto a regulaciones locales sobre venta directa y "
                        "publicidad de ingresos; no haga afirmaciones engañosas.\n"
                        "• CED no es un patrocinador oficial de PM International ni "
                        "garantiza aceptación, rangos o comisiones."
                    ),
                },
            },
        },
    }
