"""Registry de módulos Capa 3."""

from __future__ import annotations

from app.modules.base_module import BaseModule
from app.modules.camera_module import CameraModule
from app.modules.image_gen_module import ImageGenModule
from app.modules.map_module import MapModule
from app.modules.memory_module import MemoryModule
from app.modules.pdf_module import PdfModule
from app.modules.prospection_module import ProspectionModule
from app.modules.publish_module import PublishModule
from app.modules.web_search_module import WebSearchModule

MODULE_ACKS: dict[str, str] = {
    "map": "Abriendo el mapa, señor.",
    "camera": "Activando cámara, señor.",
    "publish": "Un momento, señor.",
    "image_gen": "Generando imagen, señor.",
    "pdf": "Preparando el documento, señor.",
    "web_search": "Consultando, señor.",
    "prospection": "Activando prospección, señor.",
    "memory": "Un momento, señor.",
}

MODULE_OVERLAYS: dict[str, str] = {
    "map": (
        "# MÓDULO ACTIVO: NAVEGACIÓN/MAPA\n"
        "El usuario está en modo de conducción con el mapa activo.\n"
        "Responde brevemente — el usuario está conduciendo.\n"
        "Comandos: buscar lugares, seleccionar opción, iniciar ruta, cuánto falta, detener.\n"
        "NO mezcles instrucciones GPS paso a paso en tus respuestas."
    ),
    "camera": (
        "# MÓDULO ACTIVO: CÁMARA/VISIÓN\n"
        "La cámara está activa. Analiza lo que el usuario muestra.\n"
        'Si pregunta qué ves → describe con precisión.'
    ),
    "publish": (
        "# MÓDULO ACTIVO: PUBLICACIÓN EN REDES\n"
        "Flujo: caption → proponer → confirmar → publicar.\n"
        "NUNCA publiques sin confirmación explícita."
    ),
    "image_gen": (
        "# MÓDULO ACTIVO: GENERACIÓN DE IMÁGENES\n"
        "El usuario quiere crear una imagen con IA."
    ),
    "pdf": (
        "# MÓDULO ACTIVO: GENERACIÓN DE PDF\n"
        "El usuario quiere un documento PDF."
    ),
    "web_search": (
        "# MÓDULO ACTIVO: BÚSQUEDA WEB\n"
        "Información reciente de internet. Disclaimer si no hay datos."
    ),
    "prospection": (
        "# MÓDULO ACTIVO: PROSPECCIÓN/VENTAS\n"
        "Modo prospección digital activo."
    ),
    "memory": (
        "# MÓDULO ACTIVO: MEMORIA/CRM\n"
        "Registrar datos importantes del usuario."
    ),
}


def build_module(name: str) -> BaseModule:
    factories: dict[str, type[BaseModule]] = {
        "map": MapModule,
        "camera": CameraModule,
        "publish": PublishModule,
        "image_gen": ImageGenModule,
        "pdf": PdfModule,
        "web_search": WebSearchModule,
        "prospection": ProspectionModule,
        "memory": MemoryModule,
    }
    cls = factories.get(name)
    if not cls:
        raise KeyError(name)
    return cls()
