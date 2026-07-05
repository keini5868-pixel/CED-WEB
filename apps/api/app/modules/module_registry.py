"""Registry de módulos Capa 3 — overlays y factory."""

from __future__ import annotations

from app.modules.base_module import BaseModule
from app.modules.camera_module import CameraModule
from app.modules.calendar_module import CalendarModule
from app.modules.environment_module import EnvironmentModule
from app.modules.gmail_module import GmailModule
from app.modules.image_gen_module import ImageGenModule
from app.modules.map_module import MapModule
from app.modules.memory_module import MemoryModule
from app.modules.pdf_module import PdfModule
from app.modules.prospection_module import ProspectionModule
from app.modules.publish_module import PublishModule
from app.modules.web_search_module import WebSearchModule

MODULE_ACKS: dict[str, str] = {
    "calendar": "Consultando su calendario, señor.",
    "gmail": "Revisando su correo, señor.",
    "environment": "Consultando el ambiente, señor.",
    "web_search": "Consultando, señor.",
    "publish": "Un momento, señor.",
    "map": "Abriendo el mapa, señor.",
    "camera": "Activando cámara, señor.",
    "image_gen": "Generando imagen, señor.",
    "pdf": "Preparando el documento, señor.",
    "prospection": "Activando prospección, señor.",
    "memory": "Un momento, señor.",
}

MODULE_OVERLAYS: dict[str, str] = {
    "calendar": """
MÓDULO ACTIVO: GOOGLE CALENDAR
Consulta eventos (hoy, mañana, semana) o agenda citas.
Si no está conectado, indica conectar Google Calendar en configuración.
""".strip(),
    "gmail": """
MÓDULO ACTIVO: GMAIL
Lee correos importantes, lee mensajes de un remitente o envía email.
Si no está conectado, indica conectar Gmail en configuración.
""".strip(),
    "environment": """
MÓDULO ACTIVO: AMBIENTE (CLIMA Y ENTORNO)
Responde con datos actuales obtenidos por búsqueda web.
Sé breve y natural — temperatura, condición, aire o polen según la pregunta.
""".strip(),
    "web_search": """
MÓDULO ACTIVO: BÚSQUEDA WEB
Estás buscando información actual en internet.
Responde con la información más reciente.
Si no encuentras, usa conocimiento integrado con disclaimer.
NUNCA digas que vas a buscar sin ejecutar la búsqueda.
""".strip(),
    "publish": """
MÓDULO ACTIVO: PUBLICACIÓN EN REDES
El usuario quiere publicar en Facebook o Instagram.
Flujo OBLIGATORIO: generar caption → proponer → confirmar explícitamente → publicar.
NUNCA publiques sin confirmación explícita.
"dale/sí/ok" en este contexto = confirmar publicación.
""".strip(),
    "map": """
MÓDULO ACTIVO: NAVEGACIÓN/MAPA
El usuario está en modo conducción.
Responde BREVEMENTE — está conduciendo.
"dale/sí/el primero/inicia" = confirmar navegación.
NUNCA mezcles instrucciones GPS en la conversación.
""".strip(),
    "camera": """
MÓDULO ACTIVO: CÁMARA/VISIÓN
La cámara está activa y analizando.
Describe lo que ves con precisión.
Responde preguntas sobre lo que muestra la cámara.
""".strip(),
    "image_gen": """
MÓDULO ACTIVO: GENERACIÓN DE IMÁGENES
El usuario quiere crear una imagen con IA.
Genera la imagen y muéstrala al usuario.
""".strip(),
    "pdf": """
MÓDULO ACTIVO: GENERACIÓN DE PDF
El usuario quiere crear un documento PDF.
Genera el PDF y confirma automáticamente cuando esté listo.
""".strip(),
    "prospection": """
MÓDULO ACTIVO: PROSPECCIÓN/VENTAS
El usuario está buscando prospectos digitales.
Usa las herramientas de Facebook/Instagram disponibles.
Ayuda a identificar y contactar clientes potenciales.
""".strip(),
    "memory": """
MÓDULO ACTIVO: MEMORIA/CRM
El usuario quiere guardar información importante.
Registra los datos y confirma que se guardó correctamente.
""".strip(),
}

MODULE_ORDER: tuple[str, ...] = (
    "calendar",
    "gmail",
    "environment",
    "web_search",
    "publish",
    "map",
    "camera",
    "image_gen",
    "pdf",
    "prospection",
    "memory",
)


def build_module(name: str) -> BaseModule:
    factories: dict[str, type[BaseModule]] = {
        "calendar": CalendarModule,
        "gmail": GmailModule,
        "environment": EnvironmentModule,
        "web_search": WebSearchModule,
        "publish": PublishModule,
        "map": MapModule,
        "camera": CameraModule,
        "image_gen": ImageGenModule,
        "pdf": PdfModule,
        "prospection": ProspectionModule,
        "memory": MemoryModule,
    }
    cls = factories.get(name)
    if not cls:
        raise KeyError(name)
    return cls()
