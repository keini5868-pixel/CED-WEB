"""Taxonomía del cerebro interno CED — todas las ramas del conocimiento."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDomain:
    id: str
    label: str
    keywords: tuple[str, ...]
    time_sensitive: bool = False


# Ramas premium — extensible vía internal_knowledge_articles en Supabase.
KNOWLEDGE_DOMAINS: tuple[KnowledgeDomain, ...] = (
    KnowledgeDomain("negocios", "Negocios y emprendimiento", ("negocio", "empresa", "startup", "pyme", "ventas")),
    KnowledgeDomain("marketing", "Marketing digital", ("marketing", "ads", "seo", "embudo", "marca", "contenido")),
    KnowledgeDomain("redes_sociales", "Redes sociales", ("instagram", "facebook", "tiktok", "influencer", "community")),
    KnowledgeDomain("finanzas", "Finanzas personales", ("finanzas", "presupuesto", "ahorro", "inversión", "crédito")),
    KnowledgeDomain("contabilidad", "Contabilidad", ("contabilidad", "factura", "impuesto", "balance", "nómina")),
    KnowledgeDomain("economia", "Economía", ("economía", "inflación", "pib", "mercado", "recesión"), time_sensitive=True),
    KnowledgeDomain("tecnologia", "Tecnología", ("software", "hardware", "app", "digital", "computadora", "ia")),
    KnowledgeDomain("programacion", "Programación", ("código", "python", "javascript", "api", "desarrollo", "bug")),
    KnowledgeDomain("inteligencia_artificial", "Inteligencia artificial", ("ia", "machine learning", "llm", "chatgpt", "modelo")),
    KnowledgeDomain("ciberseguridad", "Ciberseguridad", ("seguridad", "hacker", "phishing", "contraseña", "vpn")),
    KnowledgeDomain("ciencia", "Ciencia general", ("ciencia", "experimento", "hipótesis", "método científico")),
    KnowledgeDomain("fisica", "Física", ("física", "energía", "gravedad", "átomo", "cuántica")),
    KnowledgeDomain("quimica", "Química", ("química", "elemento", "reacción", "molécula")),
    KnowledgeDomain("biologia", "Biología", ("biología", "célula", "adn", "evolución", "ecosistema")),
    KnowledgeDomain("matematicas", "Matemáticas", ("matemática", "álgebra", "cálculo", "estadística", "probabilidad")),
    KnowledgeDomain("medicina", "Medicina general", ("medicina", "síntoma", "tratamiento", "diagnóstico", "salud")),
    KnowledgeDomain("nutricion", "Nutrición", ("nutrición", "dieta", "vitamina", "proteína", "calorías")),
    KnowledgeDomain("psicologia", "Psicología", ("psicología", "ansiedad", "motivación", "hábito", "mental")),
    KnowledgeDomain("derecho", "Derecho", ("ley", "legal", "contrato", "demanda", "derechos", "jurídico")),
    KnowledgeDomain("educacion", "Educación", ("educación", "aprendizaje", "estudio", "universidad", "curso")),
    KnowledgeDomain("historia", "Historia", ("historia", "siglo", "guerra", "civilización", "revolución")),
    KnowledgeDomain("geografia", "Geografía", ("geografía", "país", "capital", "continente", "mapa")),
    KnowledgeDomain("cultura", "Cultura y arte", ("arte", "música", "literatura", "cine", "cultura")),
    KnowledgeDomain("filosofia", "Filosofía", ("filosofía", "ética", "moral", "existencia", "lógica")),
    KnowledgeDomain("religion", "Religión y espiritualidad", ("religión", "fe", "espiritual", "biblia", "oración")),
    KnowledgeDomain("deportes", "Deportes", ("deporte", "fútbol", "basket", "atleta", "entrenamiento"), time_sensitive=True),
    KnowledgeDomain("gastronomia", "Gastronomía", ("comida", "receta", "cocina", "chef", "restaurante")),
    KnowledgeDomain("viajes", "Viajes y turismo", ("viaje", "turismo", "hotel", "vuelo", "destino")),
    KnowledgeDomain("moda", "Moda y belleza", ("moda", "ropa", "estilo", "belleza", "skincare")),
    KnowledgeDomain("inmobiliaria", "Bienes raíces", ("inmobiliaria", "casa", "renta", "hipoteca", "propiedad")),
    KnowledgeDomain("recursos_humanos", "Recursos humanos", ("rh", "contratación", "equipo", "liderazgo", "clima laboral")),
    KnowledgeDomain("productividad", "Productividad", ("productividad", "organización", "tiempo", "prioridades", "gtd")),
    KnowledgeDomain("comunicacion", "Comunicación", ("comunicación", "oratoria", "presentación", "persuasión")),
    KnowledgeDomain("idiomas", "Idiomas", ("inglés", "español", "traducción", "gramática", "vocabulario")),
    KnowledgeDomain("medio_ambiente", "Medio ambiente", ("ecología", "sostenible", "clima", "reciclaje", "carbono"), time_sensitive=True),
    KnowledgeDomain("ingenieria", "Ingeniería", ("ingeniería", "diseño", "mecánica", "civil", "eléctrica")),
    KnowledgeDomain("agricultura", "Agricultura", ("agricultura", "cultivo", "ganadería", "cosecha", "rural")),
    KnowledgeDomain("automotriz", "Automotriz", ("auto", "carro", "motor", "vehículo", "mecánica automotriz")),
    KnowledgeDomain("construccion", "Construcción", ("construcción", "obra", "arquitectura", "cemento", "plano")),
    KnowledgeDomain("logistica", "Logística", ("logística", "cadena", "inventario", "envío", "almacén")),
    KnowledgeDomain("ecommerce", "Comercio electrónico", ("ecommerce", "tienda online", "shopify", "carrito", "checkout")),
    KnowledgeDomain("cripto", "Cripto y blockchain", ("bitcoin", "crypto", "blockchain", "ethereum", "wallet"), time_sensitive=True),
    KnowledgeDomain("politica", "Política y sociedad", ("política", "gobierno", "elección", "leyes", "sociedad"), time_sensitive=True),
    KnowledgeDomain("noticias", "Noticias y actualidad", ("noticia", "hoy", "actualidad", "última hora"), time_sensitive=True),
    KnowledgeDomain("clima", "Clima", ("clima", "tiempo", "temperatura", "pronóstico", "lluvia"), time_sensitive=True),
)

DOMAIN_BY_ID = {d.id: d for d in KNOWLEDGE_DOMAINS}


def classify_domain(query: str) -> KnowledgeDomain | None:
    """Clasifica la rama más probable por palabras clave."""
    q = (query or "").lower()
    if not q:
        return None
    best: KnowledgeDomain | None = None
    best_score = 0
    for domain in KNOWLEDGE_DOMAINS:
        score = sum(1 for kw in domain.keywords if kw in q)
        if score > best_score:
            best_score = score
            best = domain
    return best if best_score > 0 else None
